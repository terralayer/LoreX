from __future__ import annotations

from lorex.domain import ReleaseCandidate

_AUDIO_EXTENSIONS = (".m4b", ".m4a", ".mp3", ".flac", ".aac")
_ARCHIVE_EXTENSION = ".archive"
_POSITIVE_TERMS = ("audiobook", "unabridged", "narrated", "narrator")
_NEGATIVE_TERMS = ("1080p", "2160p", "x264", "x265", ".mkv", ".avi", "bluray", "web-dl", "game", "software")


def classify_audiobook(candidate: ReleaseCandidate) -> float:
    subject = candidate.subject_stem.casefold()
    score = 0.0

    if subject.endswith(_AUDIO_EXTENSIONS) or subject.endswith(_ARCHIVE_EXTENSION):
        score += 0.7
    if any(term in subject for term in _POSITIVE_TERMS):
        score += 0.2
    # The source group is useful positive evidence after the payload filename
    # has been extracted from noisy yEnc overview subjects.
    if any("audiobook" in header.group.casefold() for header in candidate.headers):
        score += 0.2
    if subject.count(" - ") >= 2:
        score += 0.1
    if any(term in subject for term in _NEGATIVE_TERMS):
        score -= 0.8

    # Classification thresholds are decimal policy values; normalize tiny
    # binary floating-point artifacts before applying those thresholds.
    return round(max(0.0, min(1.0, score)), 3)
