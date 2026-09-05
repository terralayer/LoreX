from __future__ import annotations

import importlib


def _load_search_module():
    try:
        return importlib.import_module("lorex.services.on_demand_search")
    except ModuleNotFoundError as exc:
        raise AssertionError("on-demand audiobook search service is not implemented") from exc


def test_query_expansion_uses_book_metadata_without_global_crawling() -> None:
    search = _load_search_module()

    request = search.BookSearchRequest(
        title="Project Hail Mary",
        author="Andy Weir",
        narrator="Ray Porter",
        series=None,
        series_number=None,
        isbn="9780593395561",
        asin="B08GB58KD5",
    )

    queries = search.expand_queries(request)

    assert "Project Hail Mary" in queries
    assert "Project Hail Mary Andy Weir" in queries
    assert "Andy Weir Project Hail Mary" in queries
    assert "Project.Hail.Mary" in queries
    assert "Project_Hail_Mary" in queries
    assert "Project Hail Mary Ray Porter" in queries
    assert "Project Hail Mary m4b" in queries
    assert "Project Hail Mary audiobook" in queries
    assert "9780593395561" in queries
    assert "B08GB58KD5" in queries
    assert len(queries) == len(set(queries))
    assert len(queries) <= 30


def test_candidate_scoring_promotes_title_author_and_audio_evidence() -> None:
    search = _load_search_module()

    request = search.BookSearchRequest(title="Project Hail Mary", author="Andy Weir")
    candidate = search.SearchCandidate(
        id="release-1",
        title="Andy Weir - Project Hail Mary [M4B]",
        author="Andy Weir",
        narrator=None,
        format="m4b",
        size=812_000_000,
        completion=0.99,
        source_subject="Andy.Weir.Project.Hail.Mary.M4B",
        files=("Andy Weir - Project Hail Mary.m4b", "cover.jpg"),
    )

    scored = search.score_candidate(request, candidate)

    assert scored.score >= 80
    assert scored.bucket == "likely"
    assert "title" in scored.reasons
    assert "author" in scored.reasons
    assert "audio" in scored.reasons


def test_candidate_scoring_rejects_non_audiobook_false_positive() -> None:
    search = _load_search_module()

    request = search.BookSearchRequest(title="Project Hail Mary", author="Andy Weir")
    candidate = search.SearchCandidate(
        id="release-2",
        title="Project Hail Mary",
        author="Andy Weir",
        narrator=None,
        format="unknown",
        size=4_000_000_000,
        completion=1.0,
        source_subject="Project.Hail.Mary.2160p.WEB-DL",
        files=("Project.Hail.Mary.2160p.mkv",),
    )

    scored = search.score_candidate(request, candidate)

    assert scored.score < 60
    assert scored.bucket == "hidden"


def test_dedupe_prefers_more_complete_candidate() -> None:
    search = _load_search_module()

    candidates = [
        search.SearchCandidate(
            id="a",
            title="Project Hail Mary",
            author="Andy Weir",
            format="m4b",
            size=800_000_000,
            completion=0.82,
            source_subject="Project.Hail.Mary.m4b",
        ),
        search.SearchCandidate(
            id="b",
            title="Project Hail Mary",
            author="Andy Weir",
            format="m4b",
            size=805_000_000,
            completion=0.99,
            source_subject="Andy.Weir.Project.Hail.Mary.m4b",
        ),
    ]

    deduped = search.dedupe_candidates(candidates)

    assert [item.id for item in deduped] == ["b"]


def test_strong_match_stops_further_query_execution() -> None:
    search = _load_search_module()

    request = search.BookSearchRequest(title="Project Hail Mary", author="Andy Weir")
    calls: list[str] = []

    def provider(query: str):
        calls.append(query)
        if len(calls) == 2:
            return [
                search.SearchCandidate(
                    id="strong",
                    title="Project Hail Mary",
                    author="Andy Weir",
                    format="m4b",
                    size=800_000_000,
                    completion=1.0,
                    source_subject="Andy.Weir.Project.Hail.Mary.M4B",
                    files=("Project Hail Mary.m4b",),
                )
            ]
        return []

    result = search.execute_on_demand_search(request, provider, stop_score=90)

    assert result.stopped_early is True
    assert result.results[0].candidate.id == "strong"
    assert len(calls) == 2
