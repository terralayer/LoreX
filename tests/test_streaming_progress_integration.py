from __future__ import annotations

from pathlib import Path

from lorex.domain import ArticleHeader, DownloadJob, IndexedRelease
from lorex.downloader.engine import DownloaderConfig, StreamingDownloader
from lorex.downloader.provider import ProviderConfig, ProviderSet


class ChunkProvider:
    name = "primary"

    def stream_article(self, message_id: str):
        for _ in range(4):
            yield b"x" * 512


class ProgressState:
    def __init__(self) -> None:
        self.progress_writes: list[int] = []

    def pending_articles(self, job_id, articles): return list(articles)
    def mark_article_started(self, *args): pass
    def mark_article_completed(self, *args): pass
    def mark_article_failed(self, *args): pass
    def mark_completed(self, *args): pass
    def mark_failed(self, *args): pass
    def record_provider_attempt(self, *args, **kwargs): pass

    def persist_job_progress(self, job_id: str, *, bytes_delta: int, articles_delta: int = 0) -> None:
        self.progress_writes.append(bytes_delta)


def test_streaming_chunks_are_coalesced_into_bounded_progress_writes(tmp_path: Path) -> None:
    providers = ProviderSet(
        [ProviderConfig("primary", "primary.example")],
        clients={"primary": ChunkProvider()},
    )
    state = ProgressState()
    downloader = StreamingDownloader(
        providers,
        state,
        DownloaderConfig(
            download_root=tmp_path,
            max_active_articles=1,
            progress_byte_threshold=1024,
            progress_time_threshold_seconds=3600.0,
        ),
    )
    release = IndexedRelease("r", "T", "A", None, "m4b", 2048, 1.0, "", "s")
    article = ArticleHeader("<a>", "s", 2048)

    downloader.download_job(DownloadJob("j", "r"), release, [article])

    assert state.progress_writes == [1024, 1024]
