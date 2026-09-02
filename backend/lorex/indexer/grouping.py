from __future__ import annotations

import re
from collections import defaultdict

from lorex.domain import ArticleHeader, ReleaseCandidate

_PART_SUFFIX = re.compile(r"\s*\[\s*\d+\s*/\s*\d+\s*\]\s*$", re.IGNORECASE)


def normalize_subject(subject: str) -> str:
    return _PART_SUFFIX.sub("", subject).strip()


def group_headers(headers: list[ArticleHeader]) -> list[ReleaseCandidate]:
    grouped: dict[str, list[ArticleHeader]] = defaultdict(list)
    for header in headers:
        grouped[normalize_subject(header.subject)].append(header)

    candidates: list[ReleaseCandidate] = []
    for subject_stem, parts in grouped.items():
        ordered = sorted(parts, key=lambda item: item.message_id)
        candidates.append(ReleaseCandidate(subject_stem=subject_stem, headers=ordered))
    return sorted(candidates, key=lambda item: item.subject_stem.casefold())
