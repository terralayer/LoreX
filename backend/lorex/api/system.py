from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from lorex.search import ReleaseSearchQuery

router = APIRouter(prefix="/api/system", tags=["system"])


class ProviderHealthResponse(BaseModel):
    provider: str
    attempts: int
    successes: int
    failures: int
    fallbacks: int
    bytes_delivered: int
    elapsed_ms_total: float
    success_rate: float | None
    throughput_mib_s: float | None


class RecentReleaseResponse(BaseModel):
    id: str
    title: str
    author: str
    narrator: str | None
    format: str
    size: int
    completion: float
    download_status: str | None
    import_status: str | None
    posted_at: datetime | None


class RecentDownloadResponse(BaseModel):
    id: str
    release_id: str
    status: str
    bytes_completed: int
    articles_completed: int
    total_articles: int
    error: str | None
    cancel_requested: bool
    completed_at: datetime | None
    updated_at: datetime
    title: str | None
    author: str | None
    release_size: int | None


class RecentActivityResponse(BaseModel):
    id: int
    kind: str
    entity_id: str | None
    message: str
    detail: str | None
    created_at: datetime


class SystemSummaryResponse(BaseModel):
    ready: bool
    configuration_issues: list[str]
    credential_key_available: bool
    providers_configured: int
    providers_enabled: int
    groups_enabled: int
    library_books: int
    total_releases: int
    downloads: dict[str, int]
    scanner_enabled: bool
    scan_interval_seconds: int | None
    scanner_groups_scanning: int
    scanner_groups_error: int
    provider_health: list[ProviderHealthResponse]
    recent_releases: list[RecentReleaseResponse]
    recent_downloads: list[RecentDownloadResponse]
    recent_activity: list[RecentActivityResponse]


def _provider_health(container, providers) -> list[ProviderHealthResponse]:
    health_reader = getattr(container.jobs, "provider_health", None)
    if health_reader is None:
        return []

    rows: list[ProviderHealthResponse] = []
    for provider in providers:
        snapshot = health_reader(provider.name)
        success_rate = snapshot.successes / snapshot.attempts if snapshot.attempts else None
        throughput = None
        if snapshot.bytes_delivered > 0 and snapshot.elapsed_ms_total > 0:
            throughput = snapshot.bytes_delivered / (snapshot.elapsed_ms_total / 1000.0) / (1024.0 * 1024.0)
        rows.append(
            ProviderHealthResponse(
                provider=provider.name,
                attempts=snapshot.attempts,
                successes=snapshot.successes,
                failures=snapshot.failures,
                fallbacks=snapshot.fallbacks,
                bytes_delivered=snapshot.bytes_delivered,
                elapsed_ms_total=snapshot.elapsed_ms_total,
                success_rate=success_rate,
                throughput_mib_s=throughput,
            )
        )
    return rows


@router.get("/summary", response_model=SystemSummaryResponse)
def system_summary(request: Request) -> SystemSummaryResponse:
    container = request.app.state.container

    provider_repo = getattr(container, "nntp_providers", None)
    providers = tuple(provider_repo.list_masked()) if provider_repo is not None else ()
    providers_enabled = sum(1 for provider in providers if provider.enabled)
    groups_enabled = sum(
        1
        for provider in providers
        if provider.enabled
        for group in provider.groups
        if group.enabled
    )

    credential_key_available = bool(getattr(container, "credential_key_available", False))
    issues: list[str] = []
    if not providers:
        issues.append("No Usenet provider is configured")
    elif providers_enabled == 0:
        issues.append("No Usenet provider is enabled")
    if providers and groups_enabled == 0:
        issues.append("No NNTP group is enabled")
    if provider_repo is not None and not credential_key_available:
        issues.append("Credential encryption key is not configured")

    runtime = getattr(container, "runtime", None)
    if runtime is not None:
        settings = runtime.scanner_settings()
        states = runtime.scanner_states()
        recent_activity = [RecentActivityResponse(**asdict(event)) for event in runtime.recent_activity(limit=8)]
        scanner_enabled = settings.enabled
        scan_interval_seconds: int | None = settings.scan_interval_seconds
        scanning = sum(1 for state in states if state.status == "scanning")
        scanner_errors = sum(1 for state in states if state.status == "error")
    else:
        recent_activity = []
        scanner_enabled = False
        scan_interval_seconds = None
        scanning = 0
        scanner_errors = 0

    release_page = container.releases.search_page(
        ReleaseSearchQuery(q="", limit=5, offset=0, sort="posted_at", order="desc")
    )
    recent_releases = [RecentReleaseResponse(**asdict(item)) for item in release_page.results]

    list_recent = getattr(container.jobs, "list_recent", None)
    recent_downloads = (
        [RecentDownloadResponse(**asdict(item)) for item in list_recent(limit=5)]
        if list_recent is not None
        else []
    )
    status_counts = getattr(container.jobs, "status_counts", None)
    downloads = status_counts() if status_counts is not None else {}

    library_count = int(container.library.count())
    release_count = int(container.releases.count()) if hasattr(container.releases, "count") else int(release_page.total)

    return SystemSummaryResponse(
        ready=credential_key_available and providers_enabled > 0 and groups_enabled > 0,
        configuration_issues=issues,
        credential_key_available=credential_key_available,
        providers_configured=len(providers),
        providers_enabled=providers_enabled,
        groups_enabled=groups_enabled,
        library_books=library_count,
        total_releases=release_count,
        downloads=downloads,
        scanner_enabled=scanner_enabled,
        scan_interval_seconds=scan_interval_seconds,
        scanner_groups_scanning=scanning,
        scanner_groups_error=scanner_errors,
        provider_health=_provider_health(container, providers),
        recent_releases=recent_releases,
        recent_downloads=recent_downloads,
        recent_activity=recent_activity,
    )
