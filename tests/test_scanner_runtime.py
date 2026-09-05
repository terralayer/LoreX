from __future__ import annotations

from threading import Event
from time import sleep

from lorex.nntp.models import NntpProvider, NntpProviderGroup
from lorex.nntp.scanner import ScanStats
from lorex.runtime_repository import ScannerSettings
from lorex.workers.nntp_scanner import run_forever, run_pass


class ProviderRepository:
    def __init__(self, provider):
        self.provider = provider

    def list_enabled(self):
        return [self.provider]


class RuntimeRepository:
    def __init__(self):
        self.started = []
        self.completed = []
        self.errors = []
        self.activity = []

    def mark_scan_started(self, provider_id, group_name):
        self.started.append((provider_id, group_name))

    def mark_scan_completed(self, provider_id, group_name, *, scanned_count, indexed_count):
        self.completed.append((provider_id, group_name, scanned_count, indexed_count))

    def mark_scan_error(self, provider_id, group_name, error):
        self.errors.append((provider_id, group_name, error))

    def append_activity(self, kind, message, *, entity_id=None, detail=None):
        self.activity.append((kind, message, entity_id, detail))


class StopAfterOneWait(Event):
    def wait(self, timeout=None):
        self.set()
        return True


class HeartbeatRuntime:
    def __init__(self, *, enabled: bool = False):
        self.enabled = enabled
        self.heartbeats: list[str] = []

    def scanner_settings(self):
        return ScannerSettings(enabled=self.enabled, scan_interval_seconds=300, scan_request_token=0)

    def touch_worker_heartbeat(self, worker_name: str):
        self.heartbeats.append(worker_name)


def test_scanner_pass_records_failure_and_continues_without_secret_leak() -> None:
    provider = NntpProvider(
        id="provider-1",
        name="Primary",
        host="news.example.test",
        username="reader",
        password="super-secret-password",
        groups=(
            NntpProviderGroup("alt.binaries.audiobooks.bad"),
            NntpProviderGroup("alt.binaries.audiobooks.good"),
        ),
    )
    runtime = RuntimeRepository()
    scanned = []

    def scan(provider_arg, group, release_repository, *, mode="live"):
        scanned.append(group.group_name)
        if group.group_name.endswith("bad"):
            raise RuntimeError("provider rejected super-secret-password")
        return ScanStats(100, 199, headers_received=100, releases_indexed=4)

    successes = run_pass(
        ProviderRepository(provider),
        object(),
        runtime,
        mode="live",
        scan_fn=scan,
    )

    assert successes == 1
    assert scanned == ["alt.binaries.audiobooks.bad", "alt.binaries.audiobooks.good"]
    assert len(runtime.started) == 2
    assert runtime.completed == [("provider-1", "alt.binaries.audiobooks.good", 100, 4)]
    assert len(runtime.errors) == 1
    assert "super-secret-password" not in runtime.errors[0][2]
    assert "***" in runtime.errors[0][2]


def test_scanner_worker_publishes_heartbeat_even_when_scanning_is_disabled() -> None:
    runtime = HeartbeatRuntime()
    stop = StopAfterOneWait()

    run_forever(
        provider_repository=object(),
        release_repository=object(),
        runtime_repository=runtime,
        stop_event=stop,
        poll_seconds=0.1,
    )

    assert runtime.heartbeats
    assert set(runtime.heartbeats) == {"nntp-scanner"}


def test_scanner_heartbeat_continues_while_scan_pass_is_busy(monkeypatch) -> None:
    runtime = HeartbeatRuntime(enabled=True)
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

    assert len(runtime.heartbeats) >= 3
    assert set(runtime.heartbeats) == {"nntp-scanner"}
