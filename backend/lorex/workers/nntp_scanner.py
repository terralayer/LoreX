from __future__ import annotations

import argparse

from lorex.db import create_engine_from_url, database_url_from_env, session_factory
from lorex.nntp.errors import NntpConfigurationError
from lorex.nntp.repository import PostgresNntpProviderRepository
from lorex.postgres_repository import PostgresReleaseRepository
from lorex.security.credentials import credential_cipher_from_env
from lorex.services.nntp_scanning import scan_provider_group_once


def run_once(provider_repository, release_repository, *, mode: str = "live") -> int:
    count = 0
    for provider in provider_repository.list_enabled():
        for group in provider.groups:
            if not group.enabled:
                continue
            scan_provider_group_once(provider, group, release_repository, mode=mode)
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LoreX live NNTP scanner")
    parser.add_argument("--once", action="store_true", help="scan each enabled provider/group once")
    parser.add_argument("--mode", choices=("live", "backfill"), default="live")
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("--once is currently required")

    database_url = database_url_from_env()
    if not database_url:
        raise NntpConfigurationError("LOREX_DATABASE_URL is required for the NNTP scanner")
    cipher = credential_cipher_from_env()
    if cipher is None:
        raise NntpConfigurationError("LOREX_CREDENTIAL_KEY is required for live NNTP scanning")

    engine = create_engine_from_url(database_url)
    try:
        sessions = session_factory(engine)
        providers = PostgresNntpProviderRepository(sessions, cipher)
        releases = PostgresReleaseRepository(sessions)
        run_once(providers, releases, mode=args.mode)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
