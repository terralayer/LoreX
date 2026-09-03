from lorex.metadata.cache import InMemoryMetadataCache
from lorex.metadata.model import BookMetadata


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_positive_cache_entry_round_trips_until_ttl_expires():
    clock = FakeClock()
    cache = InMemoryMetadataCache(clock=clock, positive_ttl=60, negative_ttl=10)
    metadata = BookMetadata(title="Project Hail Mary", authors=("Andy Weir",), source="open_library")

    cache.set_found("key", metadata)
    entry = cache.get("key")
    assert entry is not None
    assert entry.status == "found"
    assert entry.metadata == metadata

    clock.advance(60.1)
    assert cache.get("key") is None


def test_negative_cache_entry_is_short_lived_and_has_no_metadata():
    clock = FakeClock()
    cache = InMemoryMetadataCache(clock=clock, positive_ttl=60, negative_ttl=10)

    cache.set_not_found("key")
    entry = cache.get("key")
    assert entry is not None
    assert entry.status == "not_found"
    assert entry.metadata is None

    clock.advance(10.1)
    assert cache.get("key") is None


def test_default_ttls_match_locked_metadata_policy():
    cache = InMemoryMetadataCache()
    assert cache.positive_ttl == 7 * 24 * 60 * 60
    assert cache.negative_ttl == 15 * 60


def test_delete_removes_disposable_cache_state():
    cache = InMemoryMetadataCache()
    cache.set_found("key", BookMetadata(title="Book"))
    cache.delete("key")
    assert cache.get("key") is None


def test_cache_contract_has_no_transient_failure_setter():
    cache = InMemoryMetadataCache()
    assert not hasattr(cache, "set_failure")
