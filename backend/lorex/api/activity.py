from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/activity", tags=["activity"])


class ActivityEventResponse(BaseModel):
    id: int
    kind: str
    entity_id: str | None
    message: str
    detail: str | None
    created_at: datetime


class ActivityListResponse(BaseModel):
    count: int
    events: list[ActivityEventResponse]


@router.get("", response_model=ActivityListResponse)
def list_activity(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
) -> ActivityListResponse:
    runtime = getattr(request.app.state.container, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Activity storage is unavailable")
    events = runtime.recent_activity(limit=limit)
    return ActivityListResponse(
        count=len(events),
        events=[
            ActivityEventResponse(
                id=event.id,
                kind=event.kind,
                entity_id=event.entity_id,
                message=event.message,
                detail=event.detail,
                created_at=event.created_at,
            )
            for event in events
        ],
    )
