from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from lorex.db_models import ImportJobRow
from lorex.domain import ImportJob


class PostgresImportJobRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def add(self, job: ImportJob) -> ImportJob:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            statement = pg_insert(ImportJobRow).values(
                id=job.id,
                release_id=job.release_id,
                status=job.status,
                source_path=job.source_path,
                stage=job.stage,
                updated_at=now,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[ImportJobRow.id],
                set_={
                    "release_id": job.release_id,
                    "status": job.status,
                    "source_path": job.source_path,
                    "stage": job.stage,
                    "updated_at": now,
                },
            )
            session.execute(statement)
        return job

    def get(self, job_id: str) -> ImportJob | None:
        with self._sessions() as session:
            row = session.get(ImportJobRow, job_id)
            if row is None:
                return None
            return ImportJob(row.id, row.release_id, row.source_path, row.status, row.stage)

    def claim_next(self, worker_id: str) -> ImportJob | None:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            row = session.execute(
                select(ImportJobRow)
                .where(ImportJobRow.status == "queued")
                .order_by(ImportJobRow.created_order)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).scalar_one_or_none()
            if row is None:
                return None
            row.status = "processing"
            row.claimed_at = now
            row.claimed_by = worker_id
            row.started_at = row.started_at or now
            row.updated_at = now
            session.flush()
            return ImportJob(row.id, row.release_id, row.source_path, row.status, row.stage)

    def set_stage(self, job_id: str, stage: str) -> None:
        with self._sessions.begin() as session:
            session.execute(
                update(ImportJobRow)
                .where(ImportJobRow.id == job_id)
                .values(stage=stage, updated_at=datetime.now(UTC))
            )

    def mark_completed(self, job_id: str, final_path: str) -> None:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            session.execute(
                update(ImportJobRow)
                .where(ImportJobRow.id == job_id)
                .values(
                    status="completed",
                    stage="completed",
                    final_path=final_path,
                    claimed_at=None,
                    claimed_by=None,
                    completed_at=now,
                    updated_at=now,
                    error=None,
                )
            )

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._sessions.begin() as session:
            session.execute(
                update(ImportJobRow)
                .where(ImportJobRow.id == job_id)
                .values(
                    status="failed",
                    claimed_at=None,
                    claimed_by=None,
                    error=error,
                    updated_at=datetime.now(UTC),
                )
            )

    def recover_stale(self, stale_before: datetime) -> int:
        with self._sessions.begin() as session:
            result = session.execute(
                update(ImportJobRow)
                .where(
                    ImportJobRow.status == "processing",
                    ImportJobRow.claimed_at.is_not(None),
                    ImportJobRow.claimed_at < stale_before,
                )
                .values(status="queued", claimed_at=None, claimed_by=None, updated_at=datetime.now(UTC))
            )
            return int(result.rowcount or 0)
