from __future__ import annotations

from pathlib import Path

import pytest

from lorex.domain import ArticleHeader, DownloadJob, IndexedRelease
from lorex.downloader.engine import DownloaderConfig, StreamingDownloader
from lorex.downloader.provider import ArticleUnavailable, ProviderConfig, ProviderSet


class MissingProvider:
    name = "primary"

    def stream_article(self, message_id: str):
        raise ArticleUnavailable(message_id)
        yield b""


class State:
    def __init__(self) -> None:
        self.status = None

    def pending_articles(self, job_id, articles):
        return list(articles)

    def mark_article_started(self, *args):
        pass

    def mark_article_completed(self, *args):
        pass

    def mark_article_failed(self, *args):
        pass

    def mark_completed(self, job_id):
        self.status = "completed"

    def mark_failed(self, job_id):
        self.status = "failed"

    def persist_progress(self, byte_count):
        pass


def test_exhausted_provider_set_marks_job_failed_and_removes_partial_file(tmp_path: Path) -> None:
    providers = ProviderSet(
        [ProviderConfig("primary", "primary.example")],
        clients={"primary": MissingProvider()},
    )
    state = State()
    downloader = StreamingDownloader(providers, state, DownloaderConfig(download_root=tmp_path))
    release = IndexedRelease("r1", "Title", "Author", None, "m4b", 10, 1.0, "", "subject")
    article = ArticleHeader("<a1>", "subject", 10)

    with pytest.raises(ArticleUnavailable):
        downloader.download_job(DownloadJob("j1", "r1"), release, [article])

    assert state.status == "failed"
    assert not list((tmp_path / "j1").glob("*.partial")) if (tmp_path / "j1").exists() else True
