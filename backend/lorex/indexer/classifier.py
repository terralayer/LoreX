from __future__ import annotations

from lorex.domain import ReleaseCandidate

_AUDIO_EXTENSIONS = (".m4b", ".m4a", ".mp3", ".flac", ".aac")
_ARCHIVE_EXTENSION = ".archive"
_POSITIVE_TERMS = ("audiobook", "unabridged", "narrated", "narrator")
_NEGATIVE_TERMS = ("1080p", "2160p", "x264", "x265", ".mkv", ".avi", "bluray", "web-dl", "game", "software")
_SOFTWARE_ARCHIVE_MARKERS = (
    "(x64)",
    "(x86)",
    " x64 ",
    " x86 ",
    "keygen",
    "crack",
    "activator",
    "+ fix",
    "license patch",
    "portable",
    "repack",
)


def _looks_like_book_archive(subject: str) -> bool:
    stem = subject[: -len(_ARCHIVE_EXTENSION)] if subject.endswith(_ARCHIVE_EXTENSION) else subject
    return " - " in stem or " by " in stem or any(term in stem for term in _POSITIVE_TERMS)


def classify_audiobook(candidate: ReleaseCandidate) -> float:
    subject = candidate.subject_stem.casefold()
    score = 0.0

    is_audio = subject.endswith(_AUDIO_EXTENSIONS)
    is_archive = subject.endswith(_ARCHIVE_EXTENSION)

    if is_archive and any(marker in subject for marker in _SOFTWARE_ARCHIVE_MARKERS):
        return 0.0

    if is_audio:
        score += 0.7
    elif is_archive:
        # Archive/PAR2/RAR payloads are common for audiobooks, but archive
        # extension plus group name alone is not enough evidence: binary groups
        # contain cross-posted software and other unrelated payloads.
        score += 0.4
        if _looks_like_book_archive(subject):
            score += 0.3

    if any(term in subject for term in _POSITIVE_TERMS):
        score += 0.2
    if any("audiobook" in header.group.casefold() for header in candidate.headers):
        score += 0.2
    if subject.count(" - ") >= 2:
        score += 0.1
    if any(term in subject for term in _NEGATIVE_TERMS):
        score -= 0.8

    # Classification thresholds are decimal policy values; normalize tiny
    # binary floating-point artifacts before applying those thresholds.
    return round(max(0.0, min(1.0, score)), 3)
