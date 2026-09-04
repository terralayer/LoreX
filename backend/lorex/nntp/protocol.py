from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GroupInfo:
    count: int
    low: int
    high: int
    name: str


@dataclass(frozen=True, slots=True)
class OverviewRecord:
    article_number: int
    subject: str
    message_id: str
    bytes: int
