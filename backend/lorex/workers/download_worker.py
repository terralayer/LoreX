from __future__ import annotations

import argparse
import signal
from threading import Event

from lorex.db import database_url_from_env
from lorex.main import AppContainer
from lorex.nntp.errors import NntpConfigurationError
from lorex.services.download_jobs import process_next_download


def run_forever(container, *, worker_id: str = "download-worker", stop_event: Event | None = None, idle_seconds: float = 1.0) -> None:
    stop = stop_event or Event()
    while not stop.is_set():
        result = process_next_download(container, worker_id=worker_id)
        if result is None:
            stop.wait(max(0.1, min(float(idle_seconds), 5.0)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LoreX automatic download worker")
    parser.add_argument("--once", action="store_true", help="process at most one queued download and exit")
    parser.add_argument("--worker-id", default="download-worker")
    args = parser.parse_args(argv)

    database_url = database_url_from_env()
    if not database_url:
        raise NntpConfigurationError("LOREX_DATABASE_URL is required for the download worker")

    container = AppContainer.build(database_url)
    try:
        if args.once:
            process_next_download(container, worker_id=args.worker_id)
            return 0

        stop = Event()

        def stop_worker(*_args) -> None:
            stop.set()

        signal.signal(signal.SIGTERM, stop_worker)
        signal.signal(signal.SIGINT, stop_worker)
        run_forever(container, worker_id=args.worker_id, stop_event=stop)
    finally:
        container.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
