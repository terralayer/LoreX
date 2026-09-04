from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from lorex.db_models import NntpProviderGroupRow, NntpProviderRow
from lorex.nntp.models import (
    NntpProvider,
    NntpProviderGroup,
    NntpProviderSummary,
    ProviderSecretUpdate,
)
from lorex.security.credentials import CredentialCipher, CredentialError

_UNSET = object()


class PostgresNntpProviderRepository:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        cipher: CredentialCipher | None,
    ) -> None:
        self._sessions = sessions
        self._cipher = cipher

    @staticmethod
    def _validate_provider(
        *, name: str, host: str, port: int, max_connections: int
    ) -> tuple[str, str]:
        clean_name = name.strip()
        clean_host = host.strip()
        if not clean_name:
            raise ValueError("provider name must not be empty")
        if not clean_host:
            raise ValueError("provider host must not be empty")
        if not 1 <= port <= 65_535:
            raise ValueError("port must be between 1 and 65535")
        if not 1 <= max_connections <= 64:
            raise ValueError("max_connections must be between 1 and 64")
        return clean_name, clean_host

    @staticmethod
    def _normalize_groups(groups: Iterable[NntpProviderGroup]) -> tuple[NntpProviderGroup, ...]:
        normalized: dict[str, NntpProviderGroup] = {}
        for group in groups:
            clean = NntpProviderGroup(
                group_name=group.group_name,
                enabled=group.enabled,
                scan_batch_size=group.scan_batch_size,
                backfill_days=group.backfill_days,
            )
            normalized[clean.normalized_name] = clean
        return tuple(normalized.values())

    def create(
        self,
        *,
        name: str,
        host: str,
        port: int = 563,
        enabled: bool = True,
        priority: int = 100,
        fill_server: bool = False,
        max_connections: int = 4,
        username: str | None = None,
        password: str | None = None,
        groups: Iterable[NntpProviderGroup] = (),
    ) -> NntpProvider:
        clean_name, clean_host = self._validate_provider(
            name=name, host=host, port=port, max_connections=max_connections
        )
        clean_groups = self._normalize_groups(groups)
        provider_id = uuid4().hex
        now = datetime.now(UTC)
        username_encrypted = self._encrypt_optional(provider_id, "username", username)
        password_encrypted = self._encrypt_optional(provider_id, "password", password)
        try:
            with self._sessions.begin() as session:
                session.add(
                    NntpProviderRow(
                        id=provider_id,
                        name=clean_name,
                        host=clean_host,
                        port=port,
                        enabled=enabled,
                        priority=priority,
                        fill_server=fill_server,
                        max_connections=max_connections,
                        username_encrypted=username_encrypted,
                        password_encrypted=password_encrypted,
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.flush()
                self._replace_groups(session, provider_id, clean_groups)
        except IntegrityError as exc:
            raise ValueError("provider name must be unique") from exc
        provider = self.get(provider_id)
        assert provider is not None
        return provider

    def get(self, provider_id: str) -> NntpProvider | None:
        with self._sessions() as session:
            row = session.get(NntpProviderRow, provider_id)
            if row is None:
                return None
            groups = self._load_groups(session, provider_id)
            return self._provider_from_row(row, groups)

    def get_masked(self, provider_id: str) -> NntpProviderSummary | None:
        with self._sessions() as session:
            row = session.get(NntpProviderRow, provider_id)
            if row is None:
                return None
            return self._summary_from_row(row, self._load_groups(session, provider_id))

    def list_all(self) -> list[NntpProvider]:
        with self._sessions() as session:
            ids = list(session.scalars(select(NntpProviderRow.id).order_by(NntpProviderRow.name, NntpProviderRow.id)))
        return [provider for provider_id in ids if (provider := self.get(provider_id)) is not None]

    def list_masked(self) -> list[NntpProviderSummary]:
        with self._sessions() as session:
            rows = list(session.scalars(select(NntpProviderRow).order_by(NntpProviderRow.name, NntpProviderRow.id)))
            return [self._summary_from_row(row, self._load_groups(session, row.id)) for row in rows]

    def list_enabled(self) -> list[NntpProvider]:
        with self._sessions() as session:
            ids = list(
                session.scalars(
                    select(NntpProviderRow.id)
                    .where(NntpProviderRow.enabled.is_(True))
                    .order_by(NntpProviderRow.fill_server, NntpProviderRow.priority, NntpProviderRow.name)
                )
            )
        return [provider for provider_id in ids if (provider := self.get(provider_id)) is not None]

    def update(
        self,
        provider_id: str,
        *,
        name: str | object = _UNSET,
        host: str | object = _UNSET,
        port: int | object = _UNSET,
        enabled: bool | object = _UNSET,
        priority: int | object = _UNSET,
        fill_server: bool | object = _UNSET,
        max_connections: int | object = _UNSET,
        username: ProviderSecretUpdate | str | None | object = _UNSET,
        password: ProviderSecretUpdate | str | None | object = _UNSET,
        groups: Iterable[NntpProviderGroup] | object = _UNSET,
    ) -> NntpProviderSummary:
        try:
            with self._sessions.begin() as session:
                row = session.get(NntpProviderRow, provider_id)
                if row is None:
                    raise KeyError(provider_id)
                next_name = row.name if name is _UNSET else str(name)
                next_host = row.host if host is _UNSET else str(host)
                next_port = row.port if port is _UNSET else int(port)
                next_max_connections = row.max_connections if max_connections is _UNSET else int(max_connections)
                clean_name, clean_host = self._validate_provider(
                    name=next_name,
                    host=next_host,
                    port=next_port,
                    max_connections=next_max_connections,
                )
                row.name = clean_name
                row.host = clean_host
                row.port = next_port
                row.max_connections = next_max_connections
                if enabled is not _UNSET:
                    row.enabled = bool(enabled)
                if priority is not _UNSET:
                    row.priority = int(priority)
                if fill_server is not _UNSET:
                    row.fill_server = bool(fill_server)
                row.username_encrypted = self._updated_secret(provider_id, "username", row.username_encrypted, username)
                row.password_encrypted = self._updated_secret(provider_id, "password", row.password_encrypted, password)
                row.updated_at = datetime.now(UTC)
                if groups is not _UNSET:
                    assert not isinstance(groups, (str, bytes))
                    self._replace_groups(session, provider_id, self._normalize_groups(groups))
        except IntegrityError as exc:
            raise ValueError("provider name must be unique") from exc
        summary = self.get_masked(provider_id)
        assert summary is not None
        return summary

    def delete(self, provider_id: str) -> bool:
        with self._sessions.begin() as session:
            row = session.get(NntpProviderRow, provider_id)
            if row is None:
                return False
            session.delete(row)
        return True

    def _encrypt_optional(self, provider_id: str, field_name: str, value: str | None) -> str | None:
        if value is None:
            return None
        if self._cipher is None:
            raise CredentialError("credential master key is not configured")
        return self._cipher.encrypt(provider_id, field_name, value)

    def _updated_secret(
        self,
        provider_id: str,
        field_name: str,
        current: str | None,
        update: ProviderSecretUpdate | str | None | object,
    ) -> str | None:
        if update is _UNSET:
            return current
        if isinstance(update, ProviderSecretUpdate):
            if update.is_keep:
                return current
            if update.is_clear:
                return None
            assert update.value is not None
            return self._encrypt_optional(provider_id, field_name, update.value)
        if update is None:
            return current
        if isinstance(update, str):
            return self._encrypt_optional(provider_id, field_name, update)
        raise ValueError("invalid secret update")

    @staticmethod
    def _replace_groups(session: Session, provider_id: str, groups: tuple[NntpProviderGroup, ...]) -> None:
        session.execute(delete(NntpProviderGroupRow).where(NntpProviderGroupRow.provider_id == provider_id))
        for group in groups:
            session.add(
                NntpProviderGroupRow(
                    provider_id=provider_id,
                    group_name_normalized=group.normalized_name,
                    group_name=group.group_name,
                    enabled=group.enabled,
                    scan_batch_size=group.scan_batch_size,
                    backfill_days=group.backfill_days,
                )
            )

    @staticmethod
    def _group_from_row(row: NntpProviderGroupRow) -> NntpProviderGroup:
        return NntpProviderGroup(
            group_name=row.group_name,
            enabled=row.enabled,
            scan_batch_size=row.scan_batch_size,
            backfill_days=row.backfill_days,
        )

    def _load_groups(self, session: Session, provider_id: str) -> tuple[NntpProviderGroup, ...]:
        return tuple(
            self._group_from_row(group)
            for group in session.scalars(
                select(NntpProviderGroupRow)
                .where(NntpProviderGroupRow.provider_id == provider_id)
                .order_by(NntpProviderGroupRow.group_name_normalized)
            )
        )

    def _provider_from_row(self, row: NntpProviderRow, groups: tuple[NntpProviderGroup, ...]) -> NntpProvider:
        if (row.username_encrypted is not None or row.password_encrypted is not None) and self._cipher is None:
            raise CredentialError("credential master key is not configured")
        username = None if row.username_encrypted is None else self._cipher.decrypt(row.id, "username", row.username_encrypted)  # type: ignore[union-attr]
        password = None if row.password_encrypted is None else self._cipher.decrypt(row.id, "password", row.password_encrypted)  # type: ignore[union-attr]
        return NntpProvider(
            id=row.id,
            name=row.name,
            host=row.host,
            port=row.port,
            enabled=row.enabled,
            priority=row.priority,
            fill_server=row.fill_server,
            max_connections=row.max_connections,
            username=username,
            password=password,
            groups=groups,
        )

    @staticmethod
    def _summary_from_row(row: NntpProviderRow, groups: tuple[NntpProviderGroup, ...]) -> NntpProviderSummary:
        return NntpProviderSummary(
            id=row.id,
            name=row.name,
            host=row.host,
            port=row.port,
            enabled=row.enabled,
            priority=row.priority,
            fill_server=row.fill_server,
            max_connections=row.max_connections,
            username_configured=row.username_encrypted is not None,
            password_configured=row.password_encrypted is not None,
            groups=groups,
        )
