from __future__ import annotations

from collections import deque

from lorex.domain import DownloadArticleState, DownloadJob
from lorex.repository import JobRepository


def test_download_article_state_defaults_to_pending() -> None:
    state = DownloadArticleState(job_id="job-1", message_id="<article-1>")

    assert state.status == "pending"
    assert state.bytes_completed == 0
    assert state.provider is None
    assert state.attempts == 0


def test_in_memory_queue_is_fifo_and_not_list_backed() -> None:
    repository = JobRepository()
    repository.add(DownloadJob(id="job-1", release_id="release-1"))
    repository.add(DownloadJob(id="job-2", release_id="release-2"))

    assert isinstance(repository._items, deque)
    assert repository.claim_next("worker-a").id == "job-1"
    assert repository.claim_next("worker-a").id == "job-2"
    assert repository.claim_next("worker-a") is None
