from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/indexer", tags=["indexer"])


class IndexerSettingsPatch(BaseModel):
    enabled: bool | None = None
    scan_interval_seconds: int | None = Field(None, ge=10, le=86_400)


class IndexerSettingsResponse(BaseModel):
    enabled: bool
    scan_interval_seconds: int
    scan_request_token: int


class IndexerGroupStatus(BaseModel):
    provider_id: str
    provider_name: str
    provider_enabled: bool
    group_name: str
    group_enabled: bool
    scan_batch_size: int
    backfill_days: int
    status: str
    checkpoint_article: int | None
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_error: str | None
    last_scanned_count: int
    last_indexed_count: int


class IndexerStatusResponse(IndexerSettingsResponse):
    groups: list[IndexerGroupStatus]


class ScanNowResponse(BaseModel):
    status: str
    scan_request_token: int


def _runtime(request: Request):
    runtime = getattr(request.app.state.container, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Indexer runtime storage is unavailable")
    return runtime


def _providers(request: Request):
    providers = getattr(request.app.state.container, "nntp_providers", None)
    if providers is None:
        raise HTTPException(status_code=503, detail="NNTP provider storage is unavailable")
    return providers


@router.get("/status", response_model=IndexerStatusResponse)
def indexer_status(request: Request) -> IndexerStatusResponse:
    runtime = _runtime(request)
    settings = runtime.scanner_settings()
    state_by_key = {(item.provider_id, item.group_name.casefold()): item for item in runtime.scanner_states()}

    groups: list[IndexerGroupStatus] = []
    for provider in _providers(request).list_masked():
        for group in provider.groups:
            state = state_by_key.get((provider.id, group.group_name.casefold()))
            checkpoint = request.app.state.container.releases.get_checkpoint(provider.id, group.group_name)
            groups.append(
                IndexerGroupStatus(
                    provider_id=provider.id,
                    provider_name=provider.name,
                    provider_enabled=provider.enabled,
                    group_name=group.group_name,
                    group_enabled=group.enabled,
                    scan_batch_size=group.scan_batch_size,
                    backfill_days=group.backfill_days,
                    status=state.status if state is not None else "idle",
                    checkpoint_article=checkpoint.article_number if checkpoint is not None else None,
                    last_started_at=state.last_started_at if state is not None else None,
                    last_completed_at=state.last_completed_at if state is not None else None,
                    last_error=state.last_error if state is not None else None,
                    last_scanned_count=state.last_scanned_count if state is not None else 0,
                    last_indexed_count=state.last_indexed_count if state is not None else 0,
                )
            )

    return IndexerStatusResponse(
        enabled=settings.enabled,
        scan_interval_seconds=settings.scan_interval_seconds,
        scan_request_token=settings.scan_request_token,
        groups=groups,
    )


@router.patch("/settings", response_model=IndexerSettingsResponse)
def update_indexer_settings(payload: IndexerSettingsPatch, request: Request) -> IndexerSettingsResponse:
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail="At least one indexer setting is required")
    try:
        settings = _runtime(request).update_scanner_settings(
            enabled=payload.enabled if "enabled" in payload.model_fields_set else None,
            scan_interval_seconds=(
                payload.scan_interval_seconds if "scan_interval_seconds" in payload.model_fields_set else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return IndexerSettingsResponse(
        enabled=settings.enabled,
        scan_interval_seconds=settings.scan_interval_seconds,
        scan_request_token=settings.scan_request_token,
    )


@router.post("/scan-now", status_code=status.HTTP_202_ACCEPTED, response_model=ScanNowResponse)
def request_scan_now(request: Request) -> ScanNowResponse:
    token = _runtime(request).request_scan_now()
    return ScanNowResponse(status="requested", scan_request_token=token)
