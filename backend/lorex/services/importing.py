from __future__ import annotations

from typing import Any, Callable

from lorex.domain import DownloadResult


def run_import_once(
    repository: Any,
    pipeline: Any,
    result_loader: Callable[[str], DownloadResult],
    worker_id: str,
) -> bool:
    job = repository.claim_next(worker_id)
    if job is None:
        return False
    try:
        result = result_loader(job.release_id)
        pipeline.process(job, result)
    except Exception as exc:
        repository.mark_failed(job.id, error=str(exc))
    return True
