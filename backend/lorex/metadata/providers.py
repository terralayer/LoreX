from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import httpx

from lorex.metadata.model import BookMetadata, MetadataLookup, ProviderOutcome


def _isbn(value: str | None) -> str:
    if not value:
        return ""
    return "".join(character for character in value if character.isdigit() or character in "Xx").upper()


class ProviderError(RuntimeError):
    def __init__(
        self,
        provider: str,
        reason: str,
        *,
        status_code: int | None = None,
        transient: bool = True,
    ) -> None:
        self.provider = provider
        self.reason = reason
        self.status_code = status_code
        self.transient = transient
        detail = f"HTTP {status_code}" if status_code is not None else reason
        super().__init__(f"{provider} metadata request failed ({detail})")


class MetadataProvider(Protocol):
    name: str

    def lookup(self, lookup: MetadataLookup) -> ProviderOutcome: ...


class ProviderClient:
    def __init__(
        self,
        *,
        provider: str,
        client: httpx.Client,
        sleeper: Callable[[float], None],
        jitter: Callable[[], float],
        max_attempts: int = 3,
        max_retry_after: float = 5.0,
    ) -> None:
        self.provider = provider
        self.client = client
        self.sleeper = sleeper
        self.jitter = jitter
        self.max_attempts = max_attempts
        self.max_retry_after = max_retry_after

    def _retry_delay(self, attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(max(float(retry_after), 0.0), self.max_retry_after)
                except ValueError:
                    pass
        return min(0.25 * (2 ** (attempt - 1)) + max(self.jitter(), 0.0), self.max_retry_after)

    def get(self, url: str, *, params: dict[str, str]) -> httpx.Response:
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.client.get(url, params=params)
            except httpx.TransportError:
                if attempt == self.max_attempts:
                    raise ProviderError(self.provider, "transport failure", transient=True) from None
                self.sleeper(self._retry_delay(attempt))
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self.max_attempts:
                    raise ProviderError(
                        self.provider,
                        "upstream unavailable",
                        status_code=response.status_code,
                        transient=True,
                    )
                self.sleeper(self._retry_delay(attempt, response))
                continue

            if 400 <= response.status_code < 500 and response.status_code != 404:
                raise ProviderError(
                    self.provider,
                    "request rejected",
                    status_code=response.status_code,
                    transient=False,
                )
            return response

        raise ProviderError(self.provider, "retry budget exhausted", transient=True)


class OpenLibraryProvider:
    name = "open_library"
    endpoint = "https://openlibrary.org/search.json"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = __import__("time").sleep,
        jitter: Callable[[], float] = lambda: 0.0,
        max_retry_after: float = 5.0,
    ) -> None:
        self._owns_client = client is None
        self.http = ProviderClient(
            provider=self.name,
            client=client or httpx.Client(timeout=10.0),
            sleeper=sleeper,
            jitter=jitter,
            max_retry_after=max_retry_after,
        )

    def lookup(self, lookup: MetadataLookup) -> ProviderOutcome:
        isbn = _isbn(lookup.isbn13) or _isbn(lookup.isbn10)
        if isbn:
            params = {"isbn": isbn, "limit": "1"}
        elif lookup.title and lookup.authors:
            params = {"title": lookup.title.strip(), "author": lookup.authors[0].strip(), "limit": "1"}
        else:
            return ProviderOutcome.not_found()

        response = self.http.get(self.endpoint, params=params)
        if response.status_code == 404:
            return ProviderOutcome.not_found()
        payload = response.json()
        docs = payload.get("docs") or []
        if not docs:
            return ProviderOutcome.not_found()

        doc = docs[0]
        identifiers = [str(value) for value in doc.get("isbn") or []]
        isbn13 = next((value for value in identifiers if len(_isbn(value)) == 13), None)
        isbn10 = next((value for value in identifiers if len(_isbn(value)) == 10), None)
        cover_id = doc.get("cover_i")
        artwork_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None
        metadata = BookMetadata(
            title=str(doc.get("title") or "").strip(),
            authors=tuple(str(author).strip() for author in doc.get("author_name") or [] if str(author).strip()),
            source=self.name,
            provider_id=str(doc.get("key") or "") or None,
            published_date=str(doc["first_publish_year"]) if doc.get("first_publish_year") is not None else None,
            isbn10=_isbn(isbn10) or None,
            isbn13=_isbn(isbn13) or None,
            artwork_url=artwork_url,
        )
        if not metadata.title:
            return ProviderOutcome.not_found()
        return ProviderOutcome.found(metadata)


class GoogleBooksProvider:
    name = "google_books"
    endpoint = "https://www.googleapis.com/books/v1/volumes"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = __import__("time").sleep,
        jitter: Callable[[], float] = lambda: 0.0,
        max_retry_after: float = 5.0,
    ) -> None:
        self.api_key = api_key
        self.http = ProviderClient(
            provider=self.name,
            client=client or httpx.Client(timeout=10.0),
            sleeper=sleeper,
            jitter=jitter,
            max_retry_after=max_retry_after,
        )

    def lookup(self, lookup: MetadataLookup) -> ProviderOutcome:
        isbn = _isbn(lookup.isbn13) or _isbn(lookup.isbn10)
        if isbn:
            query = f"isbn:{isbn}"
        elif lookup.title and lookup.authors:
            query = f"intitle:{lookup.title.strip()} inauthor:{lookup.authors[0].strip()}"
        else:
            return ProviderOutcome.not_found()

        params = {"q": query, "maxResults": "1"}
        if self.api_key:
            params["key"] = self.api_key
        response = self.http.get(self.endpoint, params=params)
        if response.status_code == 404:
            return ProviderOutcome.not_found()
        payload = response.json()
        items = payload.get("items") or []
        if not items:
            return ProviderOutcome.not_found()

        item = items[0]
        info = item.get("volumeInfo") or {}
        identifiers = {
            str(entry.get("type")): str(entry.get("identifier"))
            for entry in info.get("industryIdentifiers") or []
            if entry.get("type") and entry.get("identifier")
        }
        image_links = info.get("imageLinks") or {}
        metadata = BookMetadata(
            title=str(info.get("title") or "").strip(),
            authors=tuple(str(author).strip() for author in info.get("authors") or [] if str(author).strip()),
            source=self.name,
            provider_id=str(item.get("id") or "") or None,
            subtitle=str(info.get("subtitle") or "").strip() or None,
            description=str(info.get("description") or "").strip() or None,
            published_date=str(info.get("publishedDate") or "").strip() or None,
            isbn10=_isbn(identifiers.get("ISBN_10")) or None,
            isbn13=_isbn(identifiers.get("ISBN_13")) or None,
            artwork_url=(image_links.get("large") or image_links.get("medium") or image_links.get("thumbnail")),
        )
        if not metadata.title:
            return ProviderOutcome.not_found()
        return ProviderOutcome.found(metadata)
