from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class ArchiveSafetyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_files: int
    max_extracted_bytes: int

    def __post_init__(self) -> None:
        if self.max_files <= 0 or self.max_extracted_bytes <= 0:
            raise ValueError("archive limits must be positive")


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    name: str
    size: int
    symlink_target: str | None = None


@dataclass(frozen=True, slots=True)
class ArchiveManifest:
    file_count: int
    extracted_bytes: int


def _safe_relative_path(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or any(part in {"..", ""} for part in path.parts):
        raise ArchiveSafetyError(f"unsafe archive path: {value}")
    return path


def validate_archive_members(members: list[ArchiveMember], limits: ArchiveLimits) -> ArchiveManifest:
    file_count = 0
    extracted_bytes = 0
    for member in members:
        _safe_relative_path(member.name)
        if member.symlink_target is not None:
            _safe_relative_path(member.symlink_target)
        if member.size < 0:
            raise ArchiveSafetyError("archive member size cannot be negative")
        file_count += 1
        extracted_bytes += member.size
        if file_count > limits.max_files:
            raise ArchiveSafetyError("archive file-count limit exceeded")
        if extracted_bytes > limits.max_extracted_bytes:
            raise ArchiveSafetyError("archive extracted-size limit exceeded")
    return ArchiveManifest(file_count=file_count, extracted_bytes=extracted_bytes)


class ArchiveExtractor:
    def __init__(
        self,
        runner: Any,
        list_members: Callable[[Path], list[ArchiveMember]],
        limits: ArchiveLimits,
    ) -> None:
        self.runner = runner
        self.list_members = list_members
        self.limits = limits

    def extract(self, archive: Path, target: Path) -> ArchiveManifest:
        manifest = validate_archive_members(self.list_members(archive), self.limits)
        self.runner.extract_7z(archive, target)
        return manifest
