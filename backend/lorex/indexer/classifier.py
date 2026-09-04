from __future__ import annotations

from lorex.domain import ReleaseCandidate

_AUDIO_EXTENSIONS = (".m4b", ".m4a", ".mp3", ".flac", ".aac")
_ARCHIVE_EXTENSION = ".archive"
_POSITIVE_TERMS = ("audiobook", "unabridged", "narrated", "narrator")
_NEGATIVE_TERMS = ("1080p", "2160p", "x264", "x265", ".mkv", ".avi", "bluray", "web-dl", "software")
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


def classify_audiobook(candidate: ReleaseCandidate) -> float:
    subject = candidate.subject_stem.casefold()
    score = 0.0

    is_audio = subject.endswith(_AUDIO_EXTENSIONS)
    is_archive = subject.endswith(_ARCHIVE_EXTENSION)

    # alt.binaries.audiobooks contains cross-posts. Reject strong software and
    # video signatures before the source-group bonus is considered, but do not
    # require readable author/title text: real audiobook posts are often
    # intentionally obfuscated archive names.
    if is_archive and (
        any(marker in subject for marker in _SOFTWARE_ARCHIVE_MARKERS)
        or any(term in subject for term in _NEGATIVE_TERMS)
    ):
        return 0.0

    if is_audio or is_archive:
        score += 0.7
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
