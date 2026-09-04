from __future__ import annotations

from base64 import urlsafe_b64encode
import os

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from lorex.db import create_engine_from_url, session_factory
from lorex.db_models import NntpProviderGroupRow, NntpProviderRow
from lorex.nntp.models import NntpProviderGroup, ProviderSecretUpdate
from lorex.nntp.repository import PostgresNntpProviderRepository
from lorex.security.credentials import CredentialCipher


@pytest.fixture()
def provider_repo():
    engine = create_engine_from_url(os.environ["LOREX_DATABASE_URL"])
    sessions = session_factory(engine)
    key = urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    cipher = CredentialCipher.from_base64url(key)
    with engine.begin() as connection:
        connection.exec_driver_sql("TRUNCATE nntp_provider_groups, nntp_providers CASCADE")
    try:
        yield PostgresNntpProviderRepository(sessions, cipher), sessions
    finally:
        engine.dispose()


def _create(repo: PostgresNntpProviderRepository, *, name: str = "Primary"):
    return repo.create(
        name=name,
        host="news.example.test",
        port=563,
        enabled=True,
        priority=10,
        fill_server=False,
        max_connections=8,
        username="alice",
        password="p@ss",
        groups=[NntpProviderGroup(group_name="alt.binaries.audiobooks", scan_batch_size=5000, backfill_days=365)],
    )


def test_credentials_are_ciphertext_in_database_and_plaintext_only_on_runtime_domain(provider_repo):
    repo, sessions = provider_repo
    saved = _create(repo)

    with sessions() as session:
        row = session.get(NntpProviderRow, saved.id)
        assert row is not None
        assert row.username_encrypted != "alice"
        assert row.password_encrypted != "p@ss"
        assert row.username_encrypted.startswith("v1.")
        assert row.password_encrypted.startswith("v1.")

    loaded = repo.get(saved.id)
    assert loaded is not None
    assert loaded.username == "alice"
    assert loaded.password == "p@ss"
    assert "alice" not in repr(loaded)
    assert "p@ss" not in repr(loaded)


def test_provider_id_is_stable_32_character_hex_and_groups_are_normalized(provider_repo):
    repo, sessions = provider_repo
    saved = _create(repo)
    assert len(saved.id) == 32
    int(saved.id, 16)

    repo.update(
        saved.id,
        groups=[NntpProviderGroup(group_name=" ALT.BINARIES.AUDIOBOOKS ", scan_batch_size=4000, backfill_days=90)],
    )
    loaded = repo.get(saved.id)
    assert loaded is not None
    assert len(loaded.groups) == 1
    assert loaded.groups[0].group_name == "ALT.BINARIES.AUDIOBOOKS"

    with sessions() as session:
        rows = session.scalars(select(NntpProviderGroupRow).where(NntpProviderGroupRow.provider_id == saved.id)).all()
        assert len(rows) == 1
        assert rows[0].group_name_normalized == "alt.binaries.audiobooks"


def test_update_without_secret_preserves_existing_ciphertext(provider_repo):
    repo, sessions = provider_repo
    saved = _create(repo)
    with sessions() as session:
        before = session.get(NntpProviderRow, saved.id)
        username_ciphertext = before.username_encrypted
        password_ciphertext = before.password_encrypted

    repo.update(saved.id, host="news2.example.test")

    with sessions() as session:
        after = session.get(NntpProviderRow, saved.id)
        assert after.username_encrypted == username_ciphertext
        assert after.password_encrypted == password_ciphertext
    assert repo.get(saved.id).host == "news2.example.test"


def test_explicit_secret_clear_removes_ciphertext(provider_repo):
    repo, sessions = provider_repo
    saved = _create(repo)
    repo.update(saved.id, username=ProviderSecretUpdate.clear(), password=ProviderSecretUpdate.keep())
    loaded = repo.get(saved.id)
    assert loaded is not None
    assert loaded.username is None
    assert loaded.password == "p@ss"
    with sessions() as session:
        row = session.get(NntpProviderRow, saved.id)
        assert row.username_encrypted is None
        assert row.password_encrypted is not None


def test_provider_names_are_unique_and_delete_cascades_groups(provider_repo):
    repo, sessions = provider_repo
    saved = _create(repo)
    with pytest.raises((ValueError, IntegrityError)):
        _create(repo, name="Primary")
    repo.delete(saved.id)
    assert repo.get(saved.id) is None
    with sessions() as session:
        assert session.scalars(select(NntpProviderGroupRow).where(NntpProviderGroupRow.provider_id == saved.id)).all() == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"port": 0},
        {"port": 65536},
        {"max_connections": 0},
        {"max_connections": 65},
    ],
)
def test_provider_bounds_are_enforced(provider_repo, kwargs):
    repo, _ = provider_repo
    params = dict(
        name="Invalid",
        host="news.example.test",
        port=563,
        enabled=True,
        priority=100,
        fill_server=False,
        max_connections=4,
        username=None,
        password=None,
        groups=[],
    )
    params.update(kwargs)
    with pytest.raises(ValueError):
        repo.create(**params)


@pytest.mark.parametrize(
    "group_kwargs",
    [
        {"group_name": "", "scan_batch_size": 5000, "backfill_days": 1},
        {"group_name": "alt.binaries.audiobooks", "scan_batch_size": 99, "backfill_days": 1},
        {"group_name": "alt.binaries.audiobooks", "scan_batch_size": 50001, "backfill_days": 1},
        {"group_name": "alt.binaries.audiobooks", "scan_batch_size": 5000, "backfill_days": -1},
        {"group_name": "alt.binaries.audiobooks", "scan_batch_size": 5000, "backfill_days": 10001},
    ],
)
def test_group_bounds_are_enforced(group_kwargs):
    with pytest.raises(ValueError):
        NntpProviderGroup(**group_kwargs)
