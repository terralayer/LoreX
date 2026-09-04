from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from lorex.db_models import ActivityEventRow, RuntimeSettingRow, ScannerGroupStateRow


@dataclass(frozen=True, slots=True)
class ScannerSettings:
    enabled: bool
    scan_interval_seconds: int
    scan_request_token: int


@dataclass(frozen=True, slots=True)
class ScannerGroupState:
    provider_id: str
    group_name: str
    status: str
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_error: str | None
    last_scanned_count: int
    last_indexed_count: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    id: int
    kind: str
    entity_id: str | None
    message: str
    detail: str | None
    created_at: datetime


class PostgresRuntimeRepository:
    DEFAULT_SCAN_INTERVAL_SECONDS = 300
    MIN_SCAN_INTERVAL_SECONDS = 10
    MAX_SCAN_INTERVAL_SECONDS = 86_400
    DEFAULT_WORKER_HEARTBEAT_MAX_AGE_SECONDS = 5.0

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def scanner_settings(self) -> ScannerSettings:
        keys = {"scanner_enabled", "scan_interval_seconds", "scan_request_token"}
        with self._sessions() as session:
            rows = session.execute(
                select(RuntimeSettingRow).where(RuntimeSettingRow.key.in_(keys))
            ).scalars()
            values = {row.key: row.value for row in rows}

        return ScannerSettings(
            enabled=self._parse_bool(values.get("scanner_enabled", "true")),
            scan_interval_seconds=self._parse_interval(
                values.get("scan_interval_seconds", str(self.DEFAULT_SCAN_INTERVAL_SECONDS))
            ),
            scan_request_token=self._parse_nonnegative_int(values.get("scan_request_token", "0")),
        )

    def update_scanner_settings(
        self,
        *,
        enabled: bool | None = None,
        scan_interval_seconds: int | None = None,
    ) -> ScannerSettings:
        if scan_interval_seconds is not None:
            self._validate_interval(scan_interval_seconds)
        with self._sessions.begin() as session:
            if enabled is not None:
                self._upsert_setting(session, "scanner_enabled", "true" if enabled else "false")
            if scan_interval_seconds is not None:
                self._upsert_setting(session, "scan_interval_seconds", str(scan_interval_seconds))
        return self.scanner_settings()

    def request_scan_now(self) -> int:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            row = session.get(RuntimeSettingRow, "scan_request_token", with_for_update=True)
            if row is None:
                row = RuntimeSettingRow(key="scan_request_token", value="1", updated_at=now)
                session.add(row)
                token = 1
            else:
                token = self._parse_nonnegative_int(row.value) + 1
                row.value = str(token)
                row.updated_at = now
            session.flush()
            return token

    def touch_worker_heartbeat(self, worker_name: str) -> datetime:
        now = datetime.now(UTC)
        key = self._worker_heartbeat_key(worker_name)
        with self._sessions.begin() as session:
            statement = pg_insert(RuntimeSettingRow).values(key=key, value="alive", updated_at=now)
            statement = statement.on_conflict_do_update(
                index_elements=[RuntimeSettingRow.key],
                set_={"value": "alive", "updated_at": now},
            )
            session.execute(statement)
        return now

    def worker_heartbeat(self, worker_name: str) -> datetime | None:
        key = self._worker_heartbeat_key(worker_name)
        with self._sessions() as session:
            row = session.get(RuntimeSettingRow, key)
            if row is None:
                return None
            heartbeat = row.updated_at
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=UTC)
        return heartbeat

    def worker_is_online(
        self,
        worker_name: str,
        *,
        max_age_seconds: float | None = None,
    ) -> bool:
        heartbeat = self.worker_heartbeat(worker_name)
        if heartbeat is None:
            return False
        max_age = (
            self.DEFAULT_WORKER_HEARTBEAT_MAX_AGE_SECONDS
            if max_age_seconds is None
            else max(0.1, float(max_age_seconds))
        )
        age_seconds = (datetime.now(UTC) - heartbeat).total_seconds()
        return -max_age <= age_seconds <= max_age

    def mark_scan_started(self, provider_id: str, group_name: str) -> None:
        now = datetime.now(UTC)
        values = {
            "provider_id": provider_id,
            "group_name": group_name,
            "status": "scanning",
            "last_started_at": now,
            "last_error": None,
            "updated_at": now,
        }
        with self._sessions.begin() as session:
            statement = pg_insert(ScannerGroupStateRow).values(values)
            statement = statement.on_conflict_do_update(
                index_elements=[ScannerGroupStateRow.provider_id, ScannerGroupStateRow.group_name],
                set_={
                    "status": "scanning",
                    "last_started_at": now,
                    "last_error": None,
                    "updated_at": now,
                },
            )
            session.execute(statement)

    def mark_scan_completed(
        self,
        provider_id: str,
        group_name: str,
        *,
        scanned_count: int,
        indexed_count: int,
    ) -> None:
        now = datetime.now(UTC)
        values = {
            "provider_id": provider_id,
            "group_name": group_name,
            "status": "idle",
            "last_completed_at": now,
            "last_error": None,
            "last_scanned_count": max(0, int(scanned_count)),
            "last_indexed_count": max(0, int(indexed_count)),
            "updated_at": now,
        }
        with self._sessions.begin() as session:
            statement = pg_insert(ScannerGroupStateRow).values(values)
            statement = statement.on_conflict_do_update(
                index_elements=[ScannerGroupStateRow.provider_id, ScannerGroupStateRow.group_name],
                set_={
                    "status": "idle",
                    "last_completed_at": now,
                    "last_error": None,
                    "last_scanned_count": values["last_scanned_count"],
                    "last_indexed_count": values["last_indexed_count"],
                    "updated_at": now,
                },
            )
            session.execute(statement)

    def mark_scan_error(self, provider_id: str, group_name: str, error: str) -> None:
        now = datetime.now(UTC)
        safe_error = error.strip()[:2048] or "Scanner error"
        values = {
            "provider_id": provider_id,
            "group_name": group_name,
            "status": "error",
            "last_error": safe_error,
            "updated_at": now,
        }
        with self._sessions.begin() as session:
            statement = pg_insert(ScannerGroupStateRow).values(values)
            statement = statement.on_conflict_do_update(
                index_elements=[ScannerGroupStateRow.provider_id, ScannerGroupStateRow.group_name],
                set_={"status": "error", "last_error": safe_error, "updated_at": now},
            )
            session.execute(statement)

    def scanner_states(self) -> tuple[ScannerGroupState, ...]:
        with self._sessions() as session:
            rows = session.execute(
                select(ScannerGroupStateRow).order_by(
                    ScannerGroupStateRow.provider_id,
                    ScannerGroupStateRow.group_name,
                )
            ).scalars()
            return tuple(
                ScannerGroupState(
                    provider_id=row.provider_id,
                    group_name=row.group_name,
                    status=row.status,
                    last_started_at=row.last_started_at,
                    last_completed_at=row.last_completed_at,
                    last_error=row.last_error,
                    last_scanned_count=int(row.last_scanned_count),
                    last_indexed_count=int(row.last_indexed_count),
                    updated_at=row.updated_at,
                )
                for row in rows
            )

    def append_activity(
        self,
        kind: str,
        message: str,
        *,
        entity_id: str | None = None,
        detail: str | None = None,
    ) -> ActivityEvent:
        now = datetime.now(UTC)
        row = ActivityEventRow(
            kind=kind.strip()[:32] or "system",
            entity_id=entity_id,
            message=message.strip() or "LoreX activity",
            detail=detail,
            created_at=now,
        )
        with self._sessions.begin() as session:
            session.add(row)
            session.flush()
            event = ActivityEvent(
                id=int(row.id),
                kind=row.kind,
                entity_id=row.entity_id,
                message=row.message,
                detail=row.detail,
                created_at=row.created_at,
            )
        return event

    def recent_activity(self, *, limit: int = 50) -> tuple[ActivityEvent, ...]:
        bounded_limit = max(1, min(int(limit), 200))
        with self._sessions() as session:
            rows = session.execute(
                select(ActivityEventRow)
                .order_by(ActivityEventRow.created_at.desc(), ActivityEventRow.id.desc())
                .limit(bounded_limit)
            ).scalars()
            return tuple(
                ActivityEvent(
                    id=int(row.id),
                    kind=row.kind,
                    entity_id=row.entity_id,
                    message=row.message,
                    detail=row.detail,
                    created_at=row.created_at,
                )
                for row in rows
            )

    @staticmethod
    def _worker_heartbeat_key(worker_name: str) -> str:
        normalized = worker_name.strip().lower()
        if not normalized or len(normalized) > 64:
            raise ValueError("worker_name must be between 1 and 64 characters")
        return f"worker_heartbeat:{normalized}"

    @staticmethod
    def _upsert_setting(session: Session, key: str, value: str) -> None:
        now = datetime.now(UTC)
        statement = pg_insert(RuntimeSettingRow).values(key=key, value=value, updated_at=now)
        statement = statement.on_conflict_do_update(
            index_elements=[RuntimeSettingRow.key],
            set_={"value": value, "updated_at": now},
        )
        session.execute(statement)

    @classmethod
    def _parse_interval(cls, value: str) -> int:
        try:
            interval = int(value)
        except (TypeError, ValueError):
            return cls.DEFAULT_SCAN_INTERVAL_SECONDS
        if not cls.MIN_SCAN_INTERVAL_SECONDS <= interval <= cls.MAX_SCAN_INTERVAL_SECONDS:
            return cls.DEFAULT_SCAN_INTERVAL_SECONDS
        return interval

    @staticmethod
    def _parse_nonnegative_int(value: str) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _parse_bool(value: str) -> bool:
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def _validate_interval(cls, value: int) -> None:
        if not cls.MIN_SCAN_INTERVAL_SECONDS <= int(value) <= cls.MAX_SCAN_INTERVAL_SECONDS:
            raise ValueError(
                f"scan_interval_seconds must be between {cls.MIN_SCAN_INTERVAL_SECONDS} and {cls.MAX_SCAN_INTERVAL_SECONDS}"
            )
