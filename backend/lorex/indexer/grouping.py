from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

from lorex.domain import ArticleHeader, ReleaseCandidate

_PART_SUFFIX = re.compile(r"\s*\[\s*(\d+)\s*/\s*(\d+)\s*\]\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class NormalizedHeader:
    header: ArticleHeader
    subject_stem: str
    part_number: int | None
    total_parts: int | None


def normalize_subject(subject: str) -> str:
    return _PART_SUFFIX.sub("", subject).strip()


def normalize_header(header: ArticleHeader) -> NormalizedHeader:
    match = _PART_SUFFIX.search(header.subject)
    if match is None:
        return NormalizedHeader(
            header=header,
            subject_stem=header.subject.strip(),
            part_number=None,
            total_parts=None,
        )

    part_number = int(match.group(1))
    total_parts = int(match.group(2))
    if part_number < 1 or total_parts < 1 or part_number > total_parts:
        part_number = None
        total_parts = None

    return NormalizedHeader(
        header=header,
        subject_stem=header.subject[: match.start()].strip(),
        part_number=part_number,
        total_parts=total_parts,
    )


@dataclass(slots=True)
class _PendingGroup:
    subject_stem: str
    total_parts: int | None
    numbered_parts: dict[int, ArticleHeader] = field(default_factory=dict)
    unnumbered_headers: list[ArticleHeader] = field(default_factory=list)
    seen_message_ids: set[str] = field(default_factory=set)

    def add(self, normalized: NormalizedHeader) -> None:
        message_id = normalized.header.message_id
        if message_id in self.seen_message_ids:
            return
        self.seen_message_ids.add(message_id)

        if normalized.part_number is None or normalized.total_parts is None:
            self.unnumbered_headers.append(normalized.header)
            return

        if self.total_parts is None:
            self.total_parts = normalized.total_parts
        if normalized.part_number not in self.numbered_parts:
            self.numbered_parts[normalized.part_number] = normalized.header

    @property
    def is_complete(self) -> bool:
        return self.total_parts is not None and len(self.numbered_parts) >= self.total_parts

    def to_candidate(self) -> ReleaseCandidate:
        if self.numbered_parts:
            headers = [self.numbered_parts[number] for number in sorted(self.numbered_parts)]
        else:
            headers = list(self.unnumbered_headers)
        return ReleaseCandidate(subject_stem=self.subject_stem, headers=headers)


class StreamingHeaderGrouper:
    def __init__(
        self,
        *,
        max_pending_groups: int = 4096,
        inspect_incomplete: Callable[[ReleaseCandidate], None] | None = None,
    ) -> None:
        if max_pending_groups < 1:
            raise ValueError("max_pending_groups must be at least 1")
        self.max_pending_groups = max_pending_groups
        self.inspect_incomplete = inspect_incomplete
        self._pending: OrderedDict[str, _PendingGroup] = OrderedDict()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def _inspect(self, group: _PendingGroup) -> None:
        if self.inspect_incomplete is not None:
            self.inspect_incomplete(group.to_candidate())

    def _make_room(self) -> None:
        if len(self._pending) < self.max_pending_groups:
            return
        _, evicted = self._pending.popitem(last=False)
        self._inspect(evicted)

    def feed(self, header: ArticleHeader) -> list[ReleaseCandidate]:
        normalized = normalize_header(header)
        group = self._pending.get(normalized.subject_stem)
        if group is None:
            self._make_room()
            group = _PendingGroup(
                subject_stem=normalized.subject_stem,
                total_parts=normalized.total_parts,
            )
            self._pending[normalized.subject_stem] = group
        else:
            self._pending.move_to_end(normalized.subject_stem)

        group.add(normalized)
        if not group.is_complete:
            return []

        self._pending.pop(normalized.subject_stem, None)
        return [group.to_candidate()]

    def flush(self) -> list[ReleaseCandidate]:
        completed: list[ReleaseCandidate] = []
        for group in self._pending.values():
            if group.total_parts is None:
                if group.unnumbered_headers:
                    completed.append(group.to_candidate())
            elif group.is_complete:
                completed.append(group.to_candidate())
            else:
                self._inspect(group)
        self._pending.clear()
        return completed


def group_headers(headers: list[ArticleHeader]) -> list[ReleaseCandidate]:
    if not headers:
        return []

    grouper = StreamingHeaderGrouper(max_pending_groups=max(1, len(headers)))
    candidates: list[ReleaseCandidate] = []
    for header in headers:
        candidates.extend(grouper.feed(header))
    candidates.extend(grouper.flush())
    return sorted(candidates, key=lambda item: item.subject_stem.casefold())
