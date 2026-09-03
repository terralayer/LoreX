from __future__ import annotations

from lorex.domain import ProviderHealthSnapshot


class InMemoryProviderHealth:
    def __init__(self) -> None:
        self._snapshots: dict[str, ProviderHealthSnapshot] = {}

    def record(
        self,
        provider: str,
        *,
        success: bool,
        fallback: bool,
        byte_count: int,
        elapsed_ms: float,
    ) -> None:
        snapshot = self._snapshots.get(provider, ProviderHealthSnapshot(provider=provider))
        self._snapshots[provider] = ProviderHealthSnapshot(
            provider=provider,
            attempts=snapshot.attempts + 1,
            successes=snapshot.successes + int(success),
            failures=snapshot.failures + int(not success),
            fallbacks=snapshot.fallbacks + int(fallback),
            bytes_delivered=snapshot.bytes_delivered + byte_count,
            elapsed_ms_total=snapshot.elapsed_ms_total + elapsed_ms,
        )

    def snapshot(self, provider: str) -> ProviderHealthSnapshot:
        return self._snapshots.get(provider, ProviderHealthSnapshot(provider=provider))
