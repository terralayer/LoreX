from __future__ import annotations

from hashlib import sha1
from pathlib import Path

from lorex.domain import ArticleHeader, DownloadJob, IndexedRelease
from lorex.downloader.engine import DownloaderConfig, StreamingDownloader
from lorex.downloader.provider import ProviderConfig, ProviderSet


class RepeatingChunkProvider:
    def __init__(self, chunks: int, chunk_size: int = 65536) -> None:
        self.name = "primary"
        self.chunks = chunks
        self.chunk = b"x" * chunk_size
        self.max_materialized_chunks = 0

    def stream_article(self, message_id: str):
        for _ in range(self.chunks):
            self.max_materialized_chunks = max(self.max_materialized_chunks, 1)
            yield self.chunk


class MemoryState:
    def __init__(self) -> None:
        self.completed: set[str] = set()
        self.job_status: dict[str, str] = {}
        self.cancel_requested = False

    def pending_articles(self, job_id: str, articles):
        return [article for article in articles if article.message_id not in self.completed]

    def mark_article_started(self, job_id: str, message_id: str, provider: str) -> None:
        return None

    def mark_article_completed(self, job_id: str, message_id: str, provider: str, bytes_completed: int) -> None:
        self.completed.add(message_id)

    def mark_article_failed(self, job_id: str, message_id: str, provider: str) -> None:
        return None

    def mark_completed(self, job_id: str) -> None:
        self.job_status[job_id] = "completed"

    def mark_failed(self, job_id: str) -> None:
        self.job_status[job_id] = "failed"

    def is_cancel_requested(self, job_id: str) -> bool:
        return self.cancel_requested

    def persist_progress(self, byte_count: int) -> None:
        return None


def _release() -> IndexedRelease:
    return IndexedRelease(
        id="release-1",
        title="Project Hail Mary",
        author="Andy Weir",
        narrator="Ray Porter",
        format="m4b",
        size=0,
        completion=1.0,
        nzb="",
        source_subject="subject",
    )


def _article_part_name(message_id: str) -> str:
    key = sha1(message_id.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"article-{key}.part.complete"


def test_downloader_streams_article_to_disk_without_finalizing_whole_job(tmp_path: Path) -> None:
    provider = RepeatingChunkProvider(chunks=16)
    state = MemoryState()
    providers = ProviderSet(
        [ProviderConfig("primary", "primary.example")],
        clients={"primary": provider},
    )
    downloader = StreamingDownloader(
        providers=providers,
        state=state,
        config=DownloaderConfig(download_root=tmp_path, max_active_articles=2),
    )
    article = ArticleHeader("<article-1>", "subject", 16 * 65536)

    result = downloader.download_job(DownloadJob("job-1", "release-1"), _release(), [article])

    expected = tmp_path / "job-1" / _article_part_name(article.message_id)
    assert result.size == 16 * 65536
    assert state.completed == {"<article-1>"}
    assert "job-1" not in state.job_status
    assert provider.max_materialized_chunks == 1
    assert expected.stat().st_size == 16 * 65536
    assert result.staging_dir == str(tmp_path / "job-1")
    assert result.article_paths == (str(expected),)


def test_article_paths_preserve_release_article_order_with_concurrent_downloads(tmp_path: Path) -> None:
    provider = RepeatingChunkProvider(chunks=1)
    state = MemoryState()
    providers = ProviderSet(
        [ProviderConfig("primary", "primary.example")],
        clients={"primary": provider},
    )
    downloader = StreamingDownloader(providers, state, DownloaderConfig(download_root=tmp_path, max_active_articles=2))
    articles = [
        ArticleHeader("<article-2>", "subject [2/2]", 65536),
        ArticleHeader("<article-1>", "subject [1/2]", 65536),
    ]

    result = downloader.download_job(DownloadJob("job-1", "release-1"), _release(), articles)

    assert result.article_paths == tuple(
        str(tmp_path / "job-1" / _article_part_name(article.message_id)) for article in articles
    )


def test_downloader_redownloads_completed_state_when_staging_file_is_missing(tmp_path: Path) -> None:
    provider = RepeatingChunkProvider(chunks=1)
    state = MemoryState()
    state.completed.add("<article-1>")
    providers = ProviderSet(
        [ProviderConfig("primary", "primary.example")],
        clients={"primary": provider},
    )
    downloader = StreamingDownloader(providers, state, DownloaderConfig(download_root=tmp_path))
    article = ArticleHeader("<article-1>", "subject", 65536)

    result = downloader.download_job(DownloadJob("job-1", "release-1"), _release(), [article])

    expected = tmp_path / "job-1" / _article_part_name(article.message_id)
    assert expected.is_file()
    assert result.article_paths == (str(expected),)
