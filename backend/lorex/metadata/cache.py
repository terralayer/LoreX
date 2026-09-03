from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable, Literal, Protocol

from lorex.metadata.model import BookMetadata


@dataclass(frozen=True, slots=True)
class CacheEntry:
    status: Literal["found", "not_found"]
    metadata: BookMetadata | None
    expires_at: float


class MetadataCache(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...

    def set_found(self, key: str, metadata: BookMetadata) -> None: ...

    def set_not_found(self, key: str) -> None: ...

    def delete(self, key: str) -> None: ...


class InMemoryMetadataCache:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        positive_ttl: float = 7 * 24 * 60 * 60,
        negative_ttl: float = 15 * 60,
    ) -> None:
        if positive_ttl <= 0 or negative_ttl <= 0:
            raise ValueError("cache TTLs must be positive")
        self.clock = clock
        self.positive_ttl = positive_ttl
        self.negative_ttl = negative_ttl
        self._items: dict[str, CacheEntry] = {}
        self._lock = RLock()

    def get(self, key: str) -> CacheEntry | None:
        now = self.clock()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._items.pop(key, None)
                return None
            return entry

    def set_found(self, key: str, metadata: BookMetadata) -> None:
        with self._lock:
            self._items[key] = CacheEntry(
                status="found",
                metadata=metadata,
                expires_at=self.clock() + self.positive_ttl,
            )

    def set_not_found(self, key: str) -> None:
        with self._lock:
            self._items[key] = CacheEntry(
                status="not_found",
                metadata=None,
                expires_at=self.clock() + self.negative_ttl,
            )

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)
