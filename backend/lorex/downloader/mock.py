from __future__ import annotations

from lorex.domain import DownloadResult, IndexedRelease


class MockDownloader:
    """Deterministic milestone downloader; never contacts external NNTP servers."""

    def download(self, release: IndexedRelease) -> DownloadResult:
        return DownloadResult(
            release_id=release.id,
            title=release.title,
            author=release.author,
            narrator=release.narrator,
            format=release.format,
            file_name=f"{release.title}.{release.format}",
            size=release.size,
        )
