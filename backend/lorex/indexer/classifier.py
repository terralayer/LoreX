from __future__ import annotations

from pathlib import Path

from lorex.domain import ReleaseCandidate

_AUDIO_EXTENSIONS = {".m4b", ".m4a", ".mp3", ".flac", ".aac"}
_POSITIVE_TERMS = {"audiobook", "unabridged", "narrated", "narrator"}
_NEGATIVE_TERMS = {"1080p", "2160p", "x264", "x265", ".mkv", ".avi", "bluray", "web-dl", "game", "software"}


def classify_audiobook(candidate: ReleaseCandidate) -> float:
    subject = candidate.subject_stem.casefold()
    score = 0.0

    suffix = Path(subject).suffix
    if suffix in _AUDIO_EXTENSIONS:
        score += 0.7
    if any(term in subject for term in _POSITIVE_TERMS):
        score += 0.2
    if subject.count(" - ") >= 2:
        score += 0.1
    if any(term in subject for term in _NEGATIVE_TERMS):
        score -= 0.8

    return max(0.0, min(1.0, score))
