from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time

from lorex.downloader.provider import ProviderConfig, ProviderPool


class CountingProvider:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.lock = Lock()

    def stream_article(self, message_id: str):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.02)
            yield b"x"
        finally:
            with self.lock:
                self.active -= 1


def test_provider_pool_enforces_connection_limit() -> None:
    provider = CountingProvider()
    pool = ProviderPool(ProviderConfig("primary", "primary.example", max_connections=2), provider)

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(lambda i: b"".join(pool.stream_article(f"<{i}>")), range(6)))

    assert provider.max_active <= 2
