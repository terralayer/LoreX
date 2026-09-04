from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ReleaseSort = Literal["title", "author", "narrator", "format", "size", "completion", "posted_at"]
LibrarySort = Literal["title", "author", "narrator", "format", "size"]
SortOrder = Literal["asc", "desc"]
ReleaseFormat = Literal["m4b", "m4a", "mp3", "flac", "aac"]
DownloadStatus = Literal["queued", "downloading", "completed", "failed"]
ImportStatus = Literal["pending", "importing", "imported", "failed"]


@dataclass(frozen=True, slots=True)
class ReleaseSearchQuery:
    q: str = ""
    limit: int = 50
    offset: int = 0
    sort: ReleaseSort = "title"
    order: SortOrder = "asc"
    format: ReleaseFormat | None = None
    download_status: DownloadStatus | None = None
    import_status: ImportStatus | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if self.offset < 0:
            raise ValueError("offset must be nonnegative")


@dataclass(frozen=True, slots=True)
class ReleaseSummary:
    id: str
    title: str
    author: str
    narrator: str | None
    format: str
    size: int
    completion: float
    download_status: str | None
    import_status: str | None
    posted_at: datetime | None


@dataclass(frozen=True, slots=True)
class ReleaseSearchPage:
    total: int
    limit: int
    offset: int
    results: tuple[ReleaseSummary, ...]


@dataclass(frozen=True, slots=True)
class LibrarySearchQuery:
    q: str = ""
    limit: int = 50
    offset: int = 0
    sort: LibrarySort = "title"
    order: SortOrder = "asc"

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if self.offset < 0:
            raise ValueError("offset must be nonnegative")


@dataclass(frozen=True, slots=True)
class LibrarySummary:
    id: str
    title: str
    author: str
    narrator: str | None
    format: str
    size: int


@dataclass(frozen=True, slots=True)
class LibraryPage:
    total: int
    limit: int
    offset: int
    results: tuple[LibrarySummary, ...]


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    total_releases: int
    download_statuses: dict[str, int]
    import_statuses: dict[str, int]


@dataclass(frozen=True, slots=True)
class AppDashboardSummary:
    library_books: int
    total_releases: int
    active_downloads: int
    queued_downloads: int
