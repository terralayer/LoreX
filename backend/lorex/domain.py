from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1


@dataclass(frozen=True, slots=True)
class ArticleHeader:
    message_id: str
    subject: str
    bytes: int
    group: str = "alt.binaries.audiobooks"


@dataclass(frozen=True, slots=True)
class IndexCheckpoint:
    source: str
    group: str
    article_number: int


@dataclass(slots=True)
class ReleaseCandidate:
    subject_stem: str
    headers: list[ArticleHeader] = field(default_factory=list)

    @property
    def id(self) -> str:
        source = f"{self.subject_stem}|{'|'.join(h.message_id for h in self.headers)}"
        return sha1(source.encode("utf-8")).hexdigest()[:16]

    @property
    def size(self) -> int:
        return sum(header.bytes for header in self.headers)


@dataclass(frozen=True, slots=True)
class IndexedRelease:
    id: str
    title: str
    author: str
    narrator: str | None
    format: str
    size: int
    completion: float
    nzb: str
    source_subject: str


@dataclass(frozen=True, slots=True)
class DownloadJob:
    id: str
    release_id: str
    status: str = "queued"


@dataclass(frozen=True, slots=True)
class DownloadJobView:
    id: str
    release_id: str
    status: str
    bytes_completed: int
    articles_completed: int
    total_articles: int
    error: str | None
    cancel_requested: bool
    completed_at: datetime | None
    updated_at: datetime
    title: str | None = None
    author: str | None = None
    release_size: int | None = None


@dataclass(frozen=True, slots=True)
class ImportJob:
    id: str
    release_id: str
    source_path: str
    status: str = "queued"
    stage: str = "verify"
    staging_path: str | None = None
    final_path: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadArticleState:
    job_id: str
    message_id: str
    status: str = "pending"
    bytes_completed: int = 0
    provider: str | None = None
    attempts: int = 0


@dataclass(frozen=True, slots=True)
class ProviderHealthSnapshot:
    provider: str
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    fallbacks: int = 0
    bytes_delivered: int = 0
    elapsed_ms_total: float = 0.0


@dataclass(frozen=True, slots=True)
class DownloadResult:
    release_id: str
    title: str
    author: str
    narrator: str | None
    format: str
    file_name: str
    size: int
    staging_dir: str | None = None
    article_paths: tuple[str, ...] = ()
    article_subjects: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LibraryBook:
    id: str
    title: str
    author: str
    narrator: str | None
    format: str
    path: str
    size: int
