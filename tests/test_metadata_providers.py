import httpx
import pytest

from lorex.metadata.model import MetadataLookup
from lorex.metadata.providers import GoogleBooksProvider, OpenLibraryProvider, ProviderError


def test_open_library_uses_isbn_search_and_parses_provider_neutral_metadata():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "docs": [{
                    "key": "/works/OL123W",
                    "title": "Project Hail Mary",
                    "author_name": ["Andy Weir"],
                    "first_publish_year": 2021,
                    "isbn": ["9780063279327"],
                    "cover_i": 12345,
                }]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenLibraryProvider(client=client, sleeper=lambda _: None)
    outcome = provider.lookup(MetadataLookup(isbn13="978-0-06-327932-7"))

    assert outcome.status == "found"
    assert outcome.metadata is not None
    assert outcome.metadata.title == "Project Hail Mary"
    assert outcome.metadata.authors == ("Andy Weir",)
    assert outcome.metadata.source == "open_library"
    assert requests[0].url.params["isbn"] == "9780063279327"


def test_open_library_title_author_fallback_uses_search_parameters():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"docs": []})

    provider = OpenLibraryProvider(client=httpx.Client(transport=httpx.MockTransport(handler)), sleeper=lambda _: None)
    outcome = provider.lookup(MetadataLookup(title="Project Hail Mary", authors=("Andy Weir",)))

    assert outcome.status == "not_found"
    assert seen["title"] == "Project Hail Mary"
    assert seen["author"] == "Andy Weir"


def test_google_books_uses_api_key_only_in_upstream_request_and_parses_result():
    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"items": [{
            "id": "google-1",
            "volumeInfo": {
                "title": "Project Hail Mary",
                "authors": ["Andy Weir"],
                "publishedDate": "2021-05-04",
                "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9780063279327"}],
                "imageLinks": {"thumbnail": "https://example.test/cover.jpg"},
            },
        }]})

    provider = GoogleBooksProvider(
        api_key="top-secret-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _: None,
    )
    outcome = provider.lookup(MetadataLookup(isbn13="9780063279327"))

    assert outcome.status == "found"
    assert outcome.metadata is not None
    assert outcome.metadata.provider_id == "google-1"
    assert "top-secret-key" in requested_urls[0]
    assert "top-secret-key" not in repr(outcome)


def test_transient_5xx_is_retried_and_then_succeeds():
    calls = 0
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"docs": []})

    provider = OpenLibraryProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=sleeps.append,
        jitter=lambda: 0.0,
    )
    outcome = provider.lookup(MetadataLookup(title="Book", authors=("Author",)))

    assert outcome.status == "not_found"
    assert calls == 3
    assert sleeps == [0.25, 0.5]


def test_retry_after_is_honored_but_capped():
    calls = 0
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json={"docs": []})

    provider = OpenLibraryProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=sleeps.append,
        jitter=lambda: 0.0,
        max_retry_after=5.0,
    )
    provider.lookup(MetadataLookup(title="Book", authors=("Author",)))

    assert sleeps == [5.0]


def test_non_429_4xx_is_not_retried_and_error_hides_credentials():
    calls = 0
    api_key = "do-not-leak-me"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, text="bad request")

    provider = GoogleBooksProvider(
        api_key=api_key,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _: None,
    )

    with pytest.raises(ProviderError) as exc_info:
        provider.lookup(MetadataLookup(title="Book", authors=("Author",)))

    assert calls == 1
    assert api_key not in str(exc_info.value)
    assert "400" in str(exc_info.value)


def test_transport_failures_retry_three_times_without_url_leakage():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connect failed for https://example.test/?key=secret", request=request)

    provider = GoogleBooksProvider(
        api_key="secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _: None,
        jitter=lambda: 0.0,
    )

    with pytest.raises(ProviderError) as exc_info:
        provider.lookup(MetadataLookup(title="Book", authors=("Author",)))

    assert calls == 3
    assert "secret" not in str(exc_info.value)
    assert "example.test" not in str(exc_info.value)
