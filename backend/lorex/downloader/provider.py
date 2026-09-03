from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from threading import BoundedSemaphore
from typing import Protocol


class ArticleUnavailable(Exception):
    pass


class ProviderTemporaryError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    name: str
    host: str
    port: int = 563
    priority: int = 100
    fill_server: bool = False
    max_connections: int = 4
    enabled: bool = True
    tls: bool = True

    def __post_init__(self) -> None:
        if not self.tls:
            raise ValueError("TLS is required for NNTP providers")
        if self.max_connections <= 0:
            raise ValueError("max_connections must be positive")
        if self.port <= 0:
            raise ValueError("port must be positive")


class ArticleProvider(Protocol):
    def stream_article(self, message_id: str) -> Iterator[bytes]: ...


class ProviderPool:
    def __init__(self, config: ProviderConfig, provider: ArticleProvider) -> None:
        self.config = config
        self.provider = provider
        self._semaphore = BoundedSemaphore(config.max_connections)

    def stream_article(self, message_id: str) -> Iterator[bytes]:
        self._semaphore.acquire()
        try:
            yield from self.provider.stream_article(message_id)
        finally:
            self._semaphore.release()


class ProviderSet:
    def __init__(
        self,
        configs: list[ProviderConfig],
        *,
        clients: dict[str, ArticleProvider] | None = None,
    ) -> None:
        self._configs = tuple(configs)
        clients = clients or {}
        self._pools: dict[str, ProviderPool] = {
            config.name: ProviderPool(config, clients[config.name])
            for config in self._configs
            if config.enabled and config.name in clients
        }

    def ordered(self) -> tuple[ProviderConfig, ...]:
        return tuple(
            sorted(
                (config for config in self._configs if config.enabled),
                key=lambda config: (config.fill_server, config.priority, config.name),
            )
        )

    def pool_for(self, name: str) -> ProviderPool:
        try:
            return self._pools[name]
        except KeyError as exc:
            raise RuntimeError(f"provider client is not configured: {name}") from exc

    def stream_with_fallback(self, message_id: str) -> Iterator[bytes]:
        last_error: Exception | None = None
        for config in self.ordered():
            if config.name not in self._pools:
                continue
            try:
                yield from self._pools[config.name].stream_article(message_id)
                return
            except (ArticleUnavailable, ProviderTemporaryError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ArticleUnavailable(message_id)
