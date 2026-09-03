import os
import time

from redis import Redis

from lorex.metadata.model import BookMetadata
from lorex.metadata.redis_cache import RedisLeaseCoordinator, RedisMetadataCache


def redis_client() -> Redis:
    client = Redis.from_url(os.environ["LOREX_REDIS_URL"], decode_responses=True)
    client.flushdb()
    return client


def test_redis_cache_round_trips_found_and_not_found_entries():
    client = redis_client()
    cache = RedisMetadataCache(client, positive_ttl=60, negative_ttl=10)
    metadata = BookMetadata(title="Project Hail Mary", authors=("Andy Weir",), source="open_library")

    cache.set_found("found-key", metadata)
    found = cache.get("found-key")
    assert found is not None
    assert found.status == "found"
    assert found.metadata == metadata

    cache.set_not_found("missing-key")
    missing = cache.get("missing-key")
    assert missing is not None
    assert missing.status == "not_found"
    assert missing.metadata is None


def test_redis_cache_uses_real_expiration():
    client = redis_client()
    cache = RedisMetadataCache(client, positive_ttl=1, negative_ttl=1)
    cache.set_not_found("key")
    assert cache.get("key") is not None
    time.sleep(1.1)
    assert cache.get("key") is None


def test_only_one_distributed_lease_owner_wins_for_a_key():
    client = redis_client()
    coordinator = RedisLeaseCoordinator(client, lease_ttl=5)

    first = coordinator.acquire("lorex:metadata:v1:isbn13:9780063279327")
    second = coordinator.acquire("lorex:metadata:v1:isbn13:9780063279327")

    assert first is not None
    assert second is None
    first.release()


def test_wrong_lease_token_cannot_release_another_owner():
    client = redis_client()
    coordinator = RedisLeaseCoordinator(client, lease_ttl=5)
    lease = coordinator.acquire("key")
    assert lease is not None

    coordinator._release(lease.redis_key, "wrong-token")
    assert coordinator.acquire("key") is None

    lease.release()
    assert coordinator.acquire("key") is not None


def test_expired_lease_allows_follower_recovery():
    client = redis_client()
    coordinator = RedisLeaseCoordinator(client, lease_ttl=1)
    first = coordinator.acquire("key")
    assert first is not None
    assert coordinator.acquire("key") is None

    time.sleep(1.1)
    recovered = coordinator.acquire("key")
    assert recovered is not None


def test_redis_lease_key_is_hashed_instead_of_embedding_lookup_text():
    client = redis_client()
    coordinator = RedisLeaseCoordinator(client)
    lookup_key = "lorex:metadata:v1:title-author:secret book|private author"
    lease = coordinator.acquire(lookup_key)
    assert lease is not None
    assert "secret book" not in lease.redis_key
    assert "private author" not in lease.redis_key
    lease.release()
