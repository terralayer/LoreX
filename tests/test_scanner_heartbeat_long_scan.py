from __future__ import annotations

from threading import Event
from time import sleep

from lorex.runtime_repository import ScannerSettings
from lorex.workers.nntp_scanner import run_forever


class HeartbeatRuntime:
    def __init__(self) -> None:
        self.heartbeats = 0

    def scanner_settings(self) -> ScannerSettings:
        return ScannerSettings(enabled=True, scan_interval_seconds=300, scan_request_token=0)

    def heartbeat_scanner_worker(self) -> None:
        self.heartbeats += 1


def test_scanner_heartbeat_continues_while_scan_pass_is_busy(monkeypatch) -> None:
    runtime = HeartbeatRuntime()
    stop = Event()

    def slow_scan_pass(*args, **kwargs):
        sleep(0.12)
        stop.set()
        return 1

    monkeypatch.setattr("lorex.workers.nntp_scanner.run_pass", slow_scan_pass)

    run_forever(
        provider_repository=object(),
        release_repository=object(),
        runtime_repository=runtime,
        stop_event=stop,
        poll_seconds=0.1,
        heartbeat_seconds=0.02,
    )

    assert runtime.heartbeats >= 3
