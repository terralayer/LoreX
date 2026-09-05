from __future__ import annotations

import argparse
import signal
from collections.abc import Callable
from threading import Event, Thread
from time import monotonic

from lorex.db import create_engine_from_url, database_url_from_env, session_factory
from lorex.nntp.errors import NntpConfigurationError
from lorex.nntp.repository import PostgresNntpProviderRepository
from lorex.postgres_repository import PostgresReleaseRepository
from lorex.runtime_repository import PostgresRuntimeRepository
from lorex.security.credentials import credential_cipher_from_env
from lorex.services.nntp_scanning import scan_provider_group_once


SCANNER_WORKER_NAME = "nntp-scanner"


def _safe_error(provider, exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    for secret in (getattr(provider, "username", None), getattr(provider, "password", None)):
        if secret:
            message = message.replace(secret, "***")
    return message[:2048]


def run_pass(
    provider_repository,
    release_repository,
    runtime_repository=None,
    *,
    mode: str = "live",
    scan_fn: Callable | None = None,
) -> int:
    scanner = scan_fn or scan_provider_group_once
    successes = 0
    for provider in provider_repository.list_enabled():
        for group in provider.groups:
            if not group.enabled:
                continue
            if runtime_repository is not None:
                runtime_repository.mark_scan_started(provider.id, group.group_name)
            try:
                stats = scanner(provider, group, release_repository, mode=mode)
            except Exception as exc:
                safe_error = _safe_error(provider, exc)
                if runtime_repository is not None:
                    runtime_repository.mark_scan_error(provider.id, group.group_name, safe_error)
                    runtime_repository.append_activity(
                        "scanner",
                        f"Scan failed: {provider.name} / {group.group_name}",
                        entity_id=provider.id,
                        detail=safe_error,
                    )
                continue

            successes += 1
            if runtime_repository is not None:
                runtime_repository.mark_scan_completed(
                    provider.id,
                    group.group_name,
                    scanned_count=stats.headers_received,
                    indexed_count=stats.releases_indexed,
                )
                runtime_repository.append_activity(
                    "scanner",
                    f"Scanned {provider.name} / {group.group_name}: "
                    f"{stats.headers_received} headers, {stats.releases_indexed} releases",
                    entity_id=provider.id,
                )
    return successes


def run_once(provider_repository, release_repository, *, mode: str = "live") -> int:
    return run_pass(provider_repository, release_repository, mode=mode)


def _heartbeat_loop(runtime_repository, stop_event: Event, heartbeat_seconds: float) -> None:
    interval = max(0.01, min(float(heartbeat_seconds), 60.0))
    while not stop_event.is_set():
        try:
            runtime_repository.touch_worker_heartbeat(SCANNER_WORKER_NAME)
        except Exception:
            # Heartbeat storage can fail transiently with the database. Keep retrying;
            # the API will correctly report the worker offline until a write succeeds.
            pass
        stop_event.wait(interval)


def run_forever(
    provider_repository,
    release_repository,
    runtime_repository,
    *,
    mode: str = "live",
    stop_event: Event | None = None,
    poll_seconds: float = 1.0,
    heartbeat_seconds: float = 1.0,
) -> None:
    stop = stop_event or Event()
    heartbeat_stop = Event()
    heartbeat_thread = Thread(
        target=_heartbeat_loop,
        args=(runtime_repository, heartbeat_stop, heartbeat_seconds),
        name="lorex-nntp-scanner-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()

    last_scan_at: float | None = None
    last_request_token = runtime_repository.scanner_settings().scan_request_token

    try:
        while not stop.is_set():
            settings = runtime_repository.scanner_settings()
            now = monotonic()
            due = last_scan_at is None or now - last_scan_at >= settings.scan_interval_seconds
            manually_requested = settings.scan_request_token != last_request_token

            if settings.enabled and (due or manually_requested):
                run_pass(
                    provider_repository,
                    release_repository,
                    runtime_repository,
                    mode=mode,
                )
                last_scan_at = monotonic()
                last_request_token = runtime_repository.scanner_settings().scan_request_token

            stop.wait(max(0.1, min(float(poll_seconds), 1.0)))
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=max(1.0, min(float(heartbeat_seconds), 60.0) + 1.0))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LoreX live NNTP scanner")
    parser.add_argument("--once", action="store_true", help="scan each enabled provider/group once and exit")
    parser.add_argument("--mode", choices=("live", "backfill"), default="live")
    args = parser.parse_args(argv)

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
        runtime = PostgresRuntimeRepository(sessions)
        if args.once:
            run_pass(providers, releases, runtime, mode=args.mode)
        else:
            stop = Event()

            def stop_worker(*_args) -> None:
                stop.set()

            signal.signal(signal.SIGTERM, stop_worker)
            signal.signal(signal.SIGINT, stop_worker)
            run_forever(providers, releases, runtime, mode=args.mode, stop_event=stop)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
