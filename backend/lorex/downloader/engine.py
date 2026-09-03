from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from lorex.domain import ArticleHeader, DownloadJob, DownloadResult, IndexedRelease
from lorex.downloader.progress import ProgressCoalescer
from lorex.downloader.provider import ArticleUnavailable, ProviderSet, ProviderTemporaryError


@dataclass(frozen=True, slots=True)
class DownloaderConfig:
    download_root: Path
    max_active_articles: int = 8
    progress_byte_threshold: int = 1_048_576
    progress_time_threshold_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.max_active_articles <= 0:
            raise ValueError("max_active_articles must be positive")
        if self.progress_byte_threshold <= 0:
            raise ValueError("progress_byte_threshold must be positive")
        if self.progress_time_threshold_seconds <= 0:
            raise ValueError("progress_time_threshold_seconds must be positive")


class _JobProgressSink:
    def __init__(self, state: Any, job_id: str) -> None:
        self.state = state
        self.job_id = job_id

    def persist_progress(self, byte_count: int) -> None:
        persist_job_progress = getattr(self.state, "persist_job_progress", None)
        if persist_job_progress is not None:
            persist_job_progress(self.job_id, bytes_delta=byte_count, articles_delta=0)
            return
        persist_progress = getattr(self.state, "persist_progress", None)
        if persist_progress is not None:
            persist_progress(byte_count)


class StreamingDownloader:
    def __init__(self, providers: ProviderSet, state: Any, config: DownloaderConfig) -> None:
        self.providers = providers
        self.state = state
        self.config = config

    def download_job(
        self,
        job: DownloadJob,
        release: IndexedRelease,
        articles: Iterable[ArticleHeader],
    ) -> DownloadResult:
        job_dir = self.config.download_root / job.id
        job_dir.mkdir(parents=True, exist_ok=True)
        pending = iter(self.state.pending_articles(job.id, articles))
        coalescer = ProgressCoalescer(
            self.config.progress_byte_threshold,
            self.config.progress_time_threshold_seconds,
        )
        sink = _JobProgressSink(self.state, job.id)
        downloaded_bytes = 0

        try:
            with ThreadPoolExecutor(max_workers=self.config.max_active_articles) as executor:
                active: dict[Future[tuple[int, str]], int] = {}
                next_index = 0

                def submit_next() -> bool:
                    nonlocal next_index
                    try:
                        article = next(pending)
                    except StopIteration:
                        return False
                    index = next_index
                    next_index += 1
                    future = executor.submit(self._download_article, job, article, job_dir, index)
                    active[future] = index
                    return True

                for _ in range(self.config.max_active_articles):
                    if not submit_next():
                        break

                while active:
                    done, _ = wait(tuple(active), return_when=FIRST_COMPLETED)
                    for future in done:
                        active.pop(future, None)
                        byte_count, _provider = future.result()
                        downloaded_bytes += byte_count
                        coalescer.record(byte_count)
                        coalescer.flush_if_needed(sink)
                        submit_next()

            coalescer.flush(sink)
            self.state.mark_completed(job.id)
        except Exception:
            coalescer.flush(sink)
            self.state.mark_failed(job.id)
            raise

        return DownloadResult(
            release_id=release.id,
            title=release.title,
            author=release.author,
            narrator=release.narrator,
            format=release.format,
            file_name=f"{release.title}.{release.format}",
            size=downloaded_bytes,
        )

    def _download_article(
        self,
        job: DownloadJob,
        article: ArticleHeader,
        job_dir: Path,
        index: int,
    ) -> tuple[int, str]:
        partial = job_dir / f"article-{index:06d}.partial"
        complete = job_dir / f"article-{index:06d}.part.complete"
        last_error: Exception | None = None

        for attempt_index, config in enumerate(self.providers.ordered()):
            try:
                pool = self.providers.pool_for(config.name)
            except RuntimeError:
                continue

            fallback = attempt_index > 0
            self.state.mark_article_started(job.id, article.message_id, config.name)
            started = monotonic()
            byte_count = 0
            try:
                with partial.open("wb") as handle:
                    for chunk in pool.stream_article(article.message_id):
                        if not isinstance(chunk, (bytes, bytearray, memoryview)):
                            raise TypeError("provider chunks must be bytes-like")
                        handle.write(chunk)
                        byte_count += len(chunk)
                partial.replace(complete)
                self.state.mark_article_completed(
                    job.id,
                    article.message_id,
                    config.name,
                    byte_count,
                )
                self._record_health(
                    config.name,
                    success=True,
                    fallback=fallback,
                    byte_count=byte_count,
                    elapsed_ms=(monotonic() - started) * 1000.0,
                )
                return byte_count, config.name
            except (ArticleUnavailable, ProviderTemporaryError) as exc:
                last_error = exc
                partial.unlink(missing_ok=True)
                self.state.mark_article_failed(job.id, article.message_id, config.name)
                self._record_health(
                    config.name,
                    success=False,
                    fallback=fallback,
                    byte_count=0,
                    elapsed_ms=(monotonic() - started) * 1000.0,
                )
                continue
            except Exception:
                partial.unlink(missing_ok=True)
                self.state.mark_article_failed(job.id, article.message_id, config.name)
                raise

        if last_error is not None:
            raise last_error
        raise ArticleUnavailable(article.message_id)

    def _record_health(
        self,
        provider: str,
        *,
        success: bool,
        fallback: bool,
        byte_count: int,
        elapsed_ms: float,
    ) -> None:
        record = getattr(self.state, "record_provider_attempt", None)
        if record is not None:
            record(
                provider,
                success=success,
                fallback=fallback,
                byte_count=byte_count,
                elapsed_ms=elapsed_ms,
            )
