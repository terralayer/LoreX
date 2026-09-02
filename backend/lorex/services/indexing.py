from __future__ import annotations

import re
from pathlib import Path

from lorex.domain import ArticleHeader, IndexedRelease
from lorex.indexer.classifier import classify_audiobook
from lorex.indexer.grouping import group_headers
from lorex.indexer.nzb import build_nzb
from lorex.repository import ReleaseRepository

_EXTENSION = re.compile(r"\.(m4b|m4a|mp3|flac|aac)$", re.IGNORECASE)


def _parse_identity(subject: str) -> tuple[str, str, str | None, str]:
    fmt = Path(subject).suffix.lower().lstrip(".") or "unknown"
    clean = _EXTENSION.sub("", subject).strip()
    parts = [part.strip() for part in clean.split(" - ") if part.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2], fmt
    if len(parts) == 2:
        return parts[0], parts[1], None, fmt
    return "Unknown Author", clean, None, fmt


def index_headers(headers: list[ArticleHeader], repository: ReleaseRepository) -> list[IndexedRelease]:
    indexed: list[IndexedRelease] = []
    for candidate in group_headers(headers):
        confidence = classify_audiobook(candidate)
        if confidence < 0.8:
            continue
        author, title, narrator, fmt = _parse_identity(candidate.subject_stem)
        release = IndexedRelease(
            id=candidate.id,
            title=title,
            author=author,
            narrator=narrator,
            format=fmt,
            size=candidate.size,
            completion=1.0,
            nzb=build_nzb(candidate),
            source_subject=candidate.subject_stem,
        )
        repository.add(release)
        indexed.append(release)
    return indexed
