from __future__ import annotations

from pathlib import Path

from lorex.domain import ArticleHeader, DownloadJob, IndexedRelease
from lorex.downloader.engine import DownloaderConfig, StreamingDownloader
from lorex.downloader.provider import ArticleUnavailable, ProviderConfig, ProviderSet


class FailingPrimary:
    name = "primary"
    def stream_article(self, message_id: str):
        raise ArticleUnavailable(message_id)
        yield b""


class Fill:
    name = "fill"
    def stream_article(self, message_id: str):
        yield b"fill-data"


class State:
    def __init__(self) -> None:
        self.completed: list[str] = []
    def pending_articles(self, job_id, articles): return list(articles)
    def mark_article_started(self, *args): pass
    def mark_article_completed(self, job_id, message_id, provider, bytes_completed): self.completed.append(message_id)
    def mark_article_failed(self, *args): pass
    def mark_completed(self, *args): pass
    def mark_failed(self, *args): pass
    def persist_progress(self, *args): pass


def test_downloader_falls_back_per_article_without_restarting_job(tmp_path: Path) -> None:
    providers = ProviderSet(
        [
            ProviderConfig("primary", "primary.example", priority=10),
            ProviderConfig("fill", "fill.example", priority=1, fill_server=True),
        ],
        clients={"primary": FailingPrimary(), "fill": Fill()},
    )
    state = State()
    downloader = StreamingDownloader(providers, state, DownloaderConfig(download_root=tmp_path))
    release = IndexedRelease("r", "T", "A", None, "m4b", 9, 1.0, "", "s")

    result = downloader.download_job(DownloadJob("j", "r"), release, [ArticleHeader("<a>", "s", 9)])

    assert result.size == 9
    assert state.completed == ["<a>"]
