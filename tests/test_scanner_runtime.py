from __future__ import annotations

from lorex.nntp.models import NntpProvider, NntpProviderGroup
from lorex.nntp.scanner import ScanStats
from lorex.workers.nntp_scanner import run_pass


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
