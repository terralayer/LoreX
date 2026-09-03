from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
import time

from lorex.domain import ArticleHeader, DownloadJob, IndexedRelease
from lorex.downloader.engine import DownloaderConfig, StreamingDownloader
from lorex.downloader.provider import ProviderConfig, ProviderSet


class CountingProvider:
    def __init__(self) -> None:
        self.name = "primary"
        self.active = 0
        self.max_active = 0
        self.lock = Lock()

    def stream_article(self, message_id: str):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.02)
            yield b"x" * 1024
        finally:
            with self.lock:
                self.active -= 1


class StatelessRepo:
    def pending_articles(self, job_id, articles):
        return list(articles)
    def mark_article_started(self, *args): pass
    def mark_article_completed(self, *args): pass
    def mark_article_failed(self, *args): pass
    def mark_completed(self, *args): pass
    def mark_failed(self, *args): pass
    def persist_progress(self, *args): pass


def test_global_article_concurrency_is_bounded_across_simultaneous_jobs(tmp_path: Path) -> None:
    provider = CountingProvider()
    providers = ProviderSet(
        [ProviderConfig("primary", "primary.example", max_connections=8)],
        clients={"primary": provider},
    )
    downloader = StreamingDownloader(
        providers,
        StatelessRepo(),
        DownloaderConfig(download_root=tmp_path, max_active_articles=2),
    )
    release = IndexedRelease("r", "T", "A", None, "m4b", 0, 1.0, "", "s")

    def run_job(job_number: int):
        articles = [ArticleHeader(f"<j{job_number}-a{i}>", "s", 1024) for i in range(6)]
        return downloader.download_job(DownloadJob(f"j{job_number}", "r"), release, articles)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(run_job, (1, 2)))

    assert provider.max_active <= 2
