from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Callable, Iterable, Literal

MatchBucket = Literal["likely", "possible", "hidden"]

_AUDIO_EXTENSIONS = {"m4b", "m4a", "mp3", "flac", "aac", "ogg", "opus"}
_NEGATIVE_VIDEO_TOKENS = {
    "2160p",
    "1080p",
    "720p",
    "bluray",
    "blu-ray",
    "web-dl",
    "webrip",
    "hdtv",
    "x264",
    "x265",
    "hevc",
    "mkv",
    "avi",
    "mp4",
}


@dataclass(frozen=True, slots=True)
class BookSearchRequest:
    title: str
    author: str | None = None
    narrator: str | None = None
    series: str | None = None
    series_number: str | int | None = None
    isbn: str | None = None
    asin: str | None = None


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    id: str
    title: str
    author: str | None = None
    narrator: str | None = None
    format: str = "unknown"
    size: int = 0
    completion: float = 0.0
    source_subject: str = ""
    files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: SearchCandidate
    score: int
    bucket: MatchBucket
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OnDemandSearchResult:
    queries: tuple[str, ...]
    results: tuple[ScoredCandidate, ...]
    stopped_early: bool


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _similarity(left: str | None, right: str | None) -> float:
    a = _clean(left)
    b = _clean(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        shorter = min(len(a), len(b))
        longer = max(len(a), len(b))
        return max(0.86, shorter / longer)
    return SequenceMatcher(None, a, b).ratio()


def expand_queries(request: BookSearchRequest) -> tuple[str, ...]:
    title = " ".join(request.title.split()).strip()
    author = " ".join((request.author or "").split()).strip()
    narrator = " ".join((request.narrator or "").split()).strip()
    series = " ".join((request.series or "").split()).strip()
    if not title:
        raise ValueError("book title is required")

    queries: list[str] = []

    def add(value: str | None) -> None:
        if value:
            value = " ".join(value.split()).strip()
            if value and value not in queries:
                queries.append(value)

    add(title)
    if author:
        add(f"{title} {author}")
        add(f"{author} {title}")
    add(title.replace(" ", "."))
    add(title.replace(" ", "_"))
    add(f"{title} audiobook")
    for audio_format in ("m4b", "mp3"):
        add(f"{title} {audio_format}")
    if narrator:
        add(f"{title} {narrator}")
    if series:
        add(f"{series} {title}")
        if request.series_number is not None:
            add(f"{series} {request.series_number} {title}")
    add(request.isbn)
    add(request.asin)
    return tuple(queries[:30])


def _audio_evidence(candidate: SearchCandidate) -> bool:
    if candidate.format.casefold() in _AUDIO_EXTENSIONS:
        return True
    for filename in candidate.files:
        suffix = filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""
        if suffix in _AUDIO_EXTENSIONS:
            return True
    subject = candidate.source_subject.casefold()
    return any(re.search(rf"(?:^|[^a-z0-9]){re.escape(ext)}(?:$|[^a-z0-9])", subject) for ext in _AUDIO_EXTENSIONS)


def _negative_video_evidence(candidate: SearchCandidate) -> bool:
    text = " ".join((candidate.title, candidate.source_subject, *candidate.files)).casefold()
    return any(token in text for token in _NEGATIVE_VIDEO_TOKENS)


def score_candidate(request: BookSearchRequest, candidate: SearchCandidate) -> ScoredCandidate:
    title_similarity = max(
        _similarity(request.title, candidate.title),
        _similarity(request.title, candidate.source_subject),
        *(_similarity(request.title, filename) for filename in candidate.files),
    )
    score = round(title_similarity * 55)
    reasons: list[str] = []
    if title_similarity >= 0.68:
        reasons.append("title")

    if request.author:
        author_similarity = max(
            _similarity(request.author, candidate.author),
            _similarity(request.author, candidate.title),
            _similarity(request.author, candidate.source_subject),
        )
        if author_similarity >= 0.72:
            score += 25
            reasons.append("author")
        elif author_similarity >= 0.5:
            score += 10

    if request.narrator:
        narrator_similarity = max(
            _similarity(request.narrator, candidate.narrator),
            _similarity(request.narrator, candidate.title),
            _similarity(request.narrator, candidate.source_subject),
        )
        if narrator_similarity >= 0.72:
            score += 10
            reasons.append("narrator")

    if request.series:
        series_similarity = max(
            _similarity(request.series, candidate.title),
            _similarity(request.series, candidate.source_subject),
        )
        if series_similarity >= 0.72:
            score += 8
            reasons.append("series")

    if _audio_evidence(candidate):
        score += 15
        reasons.append("audio")
    else:
        score -= 25

    if candidate.completion >= 0.98:
        score += 5
        reasons.append("complete")
    elif candidate.completion < 0.75:
        score -= 12

    if _negative_video_evidence(candidate):
        score -= 60
        reasons.append("video-negative")

    score = max(0, min(100, score))
    bucket: MatchBucket
    if score >= 80:
        bucket = "likely"
    elif score >= 60:
        bucket = "possible"
    else:
        bucket = "hidden"
    return ScoredCandidate(candidate=candidate, score=score, bucket=bucket, reasons=tuple(reasons))


def _candidate_key(candidate: SearchCandidate) -> tuple[str, str, str]:
    return (_clean(candidate.title), _clean(candidate.author), candidate.format.casefold())


def dedupe_candidates(candidates: Iterable[SearchCandidate]) -> tuple[SearchCandidate, ...]:
    best: dict[tuple[str, str, str], SearchCandidate] = {}
    for candidate in candidates:
        key = _candidate_key(candidate)
        current = best.get(key)
        if current is None or (candidate.completion, candidate.size) > (current.completion, current.size):
            best[key] = candidate
    return tuple(best.values())


def execute_on_demand_search(
    request: BookSearchRequest,
    provider: Callable[[str], Iterable[SearchCandidate]],
    *,
    stop_score: int = 95,
) -> OnDemandSearchResult:
    if not 0 <= stop_score <= 100:
        raise ValueError("stop_score must be between 0 and 100")

    queries = expand_queries(request)
    found: list[SearchCandidate] = []
    stopped_early = False
    executed_queries: list[str] = []

    for query in queries:
        executed_queries.append(query)
        found.extend(provider(query))
        deduped = dedupe_candidates(found)
        scored = sorted(
            (score_candidate(request, candidate) for candidate in deduped),
            key=lambda item: (item.score, item.candidate.completion, item.candidate.size),
            reverse=True,
        )
        if scored and scored[0].score >= stop_score:
            stopped_early = True
            break

    visible = tuple(item for item in scored if item.bucket != "hidden") if found else ()
    return OnDemandSearchResult(queries=tuple(executed_queries), results=visible, stopped_early=stopped_early)
