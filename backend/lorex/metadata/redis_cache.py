from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass
from time import monotonic

from redis import Redis

from lorex.metadata.cache import CacheEntry
from lorex.metadata.model import BookMetadata

_SCHEMA_VERSION = 1
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


def _hashed_key(prefix: str, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _metadata_from_dict(payload: dict) -> BookMetadata:
    data = dict(payload)
    data["authors"] = tuple(data.get("authors") or ())
    return BookMetadata(**data)


class RedisMetadataCache:
    def __init__(
        self,
        client: Redis,
        *,
        positive_ttl: int = 7 * 24 * 60 * 60,
        negative_ttl: int = 15 * 60,
    ) -> None:
        if positive_ttl < 1 or negative_ttl < 1:
            raise ValueError("cache TTLs must be at least one second")
        self.client = client
        self.positive_ttl = int(positive_ttl)
        self.negative_ttl = int(negative_ttl)

    def _key(self, key: str) -> str:
        return _hashed_key("lorex:metadata-cache:v1", key)

    def get(self, key: str) -> CacheEntry | None:
        redis_key = self._key(key)
        raw = self.client.get(redis_key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            if payload.get("schema") != _SCHEMA_VERSION:
                self.client.delete(redis_key)
                return None
            status = payload["status"]
            metadata_payload = payload.get("metadata")
            metadata = _metadata_from_dict(metadata_payload) if metadata_payload else None
            ttl = max(self.client.ttl(redis_key), 0)
            return CacheEntry(status=status, metadata=metadata, expires_at=monotonic() + ttl)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.client.delete(redis_key)
            return None

    def set_found(self, key: str, metadata: BookMetadata) -> None:
        payload = {
            "schema": _SCHEMA_VERSION,
            "status": "found",
            "metadata": asdict(metadata),
        }
        self.client.setex(self._key(key), self.positive_ttl, json.dumps(payload, separators=(",", ":")))

    def set_not_found(self, key: str) -> None:
        payload = {"schema": _SCHEMA_VERSION, "status": "not_found", "metadata": None}
        self.client.setex(self._key(key), self.negative_ttl, json.dumps(payload, separators=(",", ":")))

    def delete(self, key: str) -> None:
        self.client.delete(self._key(key))


@dataclass(slots=True)
class Lease:
    coordinator: "RedisLeaseCoordinator"
    redis_key: str
    token: str
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self.coordinator._release(self.redis_key, self.token)
        self._released = True

    def __enter__(self) -> "Lease":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class RedisLeaseCoordinator:
    def __init__(self, client: Redis, *, lease_ttl: int = 15) -> None:
        if lease_ttl < 1:
            raise ValueError("lease_ttl must be at least one second")
        self.client = client
        self.lease_ttl = int(lease_ttl)

    def _key(self, lookup_key: str) -> str:
        return _hashed_key("lorex:metadata-lease:v1", lookup_key)

    def acquire(self, lookup_key: str) -> Lease | None:
        redis_key = self._key(lookup_key)
        token = secrets.token_urlsafe(24)
        if not self.client.set(redis_key, token, nx=True, ex=self.lease_ttl):
            return None
        return Lease(coordinator=self, redis_key=redis_key, token=token)

    def _release(self, redis_key: str, token: str) -> bool:
        return bool(self.client.eval(_RELEASE_SCRIPT, 1, redis_key, token))
