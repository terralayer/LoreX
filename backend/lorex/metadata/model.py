from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_WHITESPACE = re.compile(r"\s+")
_IDENTIFIER_PUNCTUATION = re.compile(r"[^0-9Xx]")


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE.sub(" ", value.strip()).casefold()


def _normalize_isbn(value: str | None) -> str:
    if not value:
        return ""
    return _IDENTIFIER_PUNCTUATION.sub("", value).upper()


@dataclass(frozen=True, slots=True)
class MetadataLookup:
    title: str | None = None
    authors: tuple[str, ...] = ()
    isbn10: str | None = None
    isbn13: str | None = None
    asin: str | None = None


@dataclass(frozen=True, slots=True)
class BookMetadata:
    title: str
    authors: tuple[str, ...] = ()
    source: str = "local"
    provider_id: str | None = None
    subtitle: str | None = None
    description: str | None = None
    published_date: str | None = None
    isbn10: str | None = None
    isbn13: str | None = None
    asin: str | None = None
    artwork_url: str | None = None
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    status: Literal["found", "not_found"]
    metadata: BookMetadata | None = None

    @classmethod
    def found(cls, metadata: BookMetadata) -> "ProviderOutcome":
        return cls(status="found", metadata=metadata)

    @classmethod
    def not_found(cls) -> "ProviderOutcome":
        return cls(status="not_found")


def normalize_lookup_key(lookup: MetadataLookup) -> str:
    isbn13 = _normalize_isbn(lookup.isbn13)
    if isbn13:
        return f"lorex:metadata:v1:isbn13:{isbn13}"

    isbn10 = _normalize_isbn(lookup.isbn10)
    if isbn10:
        return f"lorex:metadata:v1:isbn10:{isbn10}"

    asin = (lookup.asin or "").strip().upper()
    if asin:
        return f"lorex:metadata:v1:asin:{asin}"

    title = _normalize_text(lookup.title)
    authors = tuple(filter(None, (_normalize_text(author) for author in lookup.authors)))
    if title and authors:
        return f"lorex:metadata:v1:title-author:{title}|{'|'.join(authors)}"

    raise ValueError("metadata lookup requires an identifier or title and author")
