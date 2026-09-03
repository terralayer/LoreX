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


def test_downloader_streams_article_to_disk_and_marks_job_complete(tmp_path: Path) -> None:
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

    assert result.size == 16 * 65536
    assert state.completed == {"<article-1>"}
    assert state.job_status["job-1"] == "completed"
    assert provider.max_materialized_chunks == 1
    assert (tmp_path / "job-1" / _article_part_name(article.message_id)).stat().st_size == 16 * 65536


def test_article_part_name_depends_on_message_id_not_pending_order(tmp_path: Path) -> None:
    provider = RepeatingChunkProvider(chunks=1)
    state = MemoryState()
    providers = ProviderSet(
        [ProviderConfig("primary", "primary.example")],
        clients={"primary": provider},
    )
    downloader = StreamingDownloader(providers, state, DownloaderConfig(download_root=tmp_path))
    article = ArticleHeader("<article-2>", "subject", 65536)

    downloader.download_job(DownloadJob("job-1", "release-1"), _release(), [article])

    assert (tmp_path / "job-1" / _article_part_name(article.message_id)).is_file()


def test_downloader_skips_completed_articles_on_resume_but_reports_full_release_bytes(tmp_path: Path) -> None:
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

    assert result.size == 65536
