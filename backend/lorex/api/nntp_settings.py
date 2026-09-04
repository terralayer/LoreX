from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from lorex.nntp.client import NntpClient
from lorex.nntp.errors import NntpAuthenticationError, NntpError, NntpTemporaryError
from lorex.nntp.models import NntpProviderGroup, ProviderSecretUpdate
from lorex.security.credentials import CredentialError

router = APIRouter(prefix="/api/settings/nntp/providers", tags=["nntp-settings"])


class ProviderGroupInput(BaseModel):
    group_name: str
    enabled: bool = True
    scan_batch_size: int = Field(5000, ge=100, le=50_000)
    backfill_days: int = Field(0, ge=0, le=10_000)

    def to_domain(self) -> NntpProviderGroup:
        return NntpProviderGroup(**self.model_dump())


class ProviderCreateInput(BaseModel):
    name: str
    host: str
    port: int = Field(563, ge=1, le=65_535)
    enabled: bool = True
    priority: int = 100
    fill_server: bool = False
    max_connections: int = Field(4, ge=1, le=64)
    username: str | None = None
    password: str | None = None
    groups: list[ProviderGroupInput] = []


class ProviderPatchInput(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = Field(None, ge=1, le=65_535)
    enabled: bool | None = None
    priority: int | None = None
    fill_server: bool | None = None
    max_connections: int | None = Field(None, ge=1, le=64)
    username: str | None = None
    password: str | None = None
    groups: list[ProviderGroupInput] | None = None


class ProviderGroupResponse(BaseModel):
    group_name: str
    enabled: bool
    scan_batch_size: int
    backfill_days: int


class ProviderResponse(BaseModel):
    id: str
    name: str
    host: str
    port: int
    enabled: bool
    priority: int
    fill_server: bool
    max_connections: int
    username_configured: bool
    password_configured: bool
    groups: list[ProviderGroupResponse]


class ProviderListResponse(BaseModel):
    count: int
    providers: list[ProviderResponse]


class ProviderTestResponse(BaseModel):
    status: str
    provider_id: str
    group: str | None = None


def _repo(request: Request):
    repo = getattr(request.app.state.container, "nntp_providers", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="NNTP provider storage is unavailable")
    return repo


def _masked(summary) -> ProviderResponse:
    return ProviderResponse(
        id=summary.id,
        name=summary.name,
        host=summary.host,
        port=summary.port,
        enabled=summary.enabled,
        priority=summary.priority,
        fill_server=summary.fill_server,
        max_connections=summary.max_connections,
        username_configured=summary.username_configured,
        password_configured=summary.password_configured,
        groups=[ProviderGroupResponse(**asdict(group)) for group in summary.groups],
    )


def _credential_error(exc: CredentialError) -> HTTPException:
    return HTTPException(status_code=503, detail="Provider credential encryption is not configured")


@router.get("", response_model=ProviderListResponse)
def list_providers(request: Request) -> ProviderListResponse:
    providers = [_masked(item) for item in _repo(request).list_masked()]
    return ProviderListResponse(count=len(providers), providers=providers)


@router.post("", status_code=201, response_model=ProviderResponse)
def create_provider(payload: ProviderCreateInput, request: Request) -> ProviderResponse:
    repo = _repo(request)
    try:
        created = repo.create(
            name=payload.name,
            host=payload.host,
            port=payload.port,
            enabled=payload.enabled,
            priority=payload.priority,
            fill_server=payload.fill_server,
            max_connections=payload.max_connections,
            username=payload.username,
            password=payload.password,
            groups=[group.to_domain() for group in payload.groups],
        )
    except CredentialError as exc:
        raise _credential_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    summary = repo.get_masked(created.id)
    assert summary is not None
    return _masked(summary)


@router.patch("/{provider_id}", response_model=ProviderResponse)
def patch_provider(provider_id: str, payload: ProviderPatchInput, request: Request) -> ProviderResponse:
    repo = _repo(request)
    changes: dict[str, object] = {}
    for field_name in (
        "name",
        "host",
        "port",
        "enabled",
        "priority",
        "fill_server",
        "max_connections",
    ):
        if field_name in payload.model_fields_set:
            value = getattr(payload, field_name)
            if value is None:
                raise HTTPException(status_code=422, detail=f"{field_name} cannot be null")
            changes[field_name] = value
    for field_name in ("username", "password"):
        if field_name in payload.model_fields_set:
            value = getattr(payload, field_name)
            if value is None:
                raise HTTPException(status_code=422, detail=f"Use the explicit clear endpoint to clear {field_name}")
            changes[field_name] = ProviderSecretUpdate.replace(value)
    if "groups" in payload.model_fields_set:
        if payload.groups is None:
            raise HTTPException(status_code=422, detail="groups cannot be null")
        changes["groups"] = [group.to_domain() for group in payload.groups]
    try:
        return _masked(repo.update(provider_id, **changes))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Provider not found") from exc
    except CredentialError as exc:
        raise _credential_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{provider_id}/test", response_model=ProviderTestResponse)
def test_provider_connection(provider_id: str, request: Request) -> ProviderTestResponse:
    container = request.app.state.container
    if not getattr(container, "credential_key_available", False):
        raise HTTPException(status_code=503, detail="Provider credential encryption is not configured")
    repo = _repo(request)
    try:
        provider = repo.get(provider_id)
    except CredentialError as exc:
        raise _credential_error(exc) from exc
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    if (provider.username is None) != (provider.password is None):
        raise HTTPException(status_code=422, detail="Provider username and password must be configured together")

    group = next((item.group_name for item in provider.groups if item.enabled), None)
    try:
        with NntpClient(provider.host, provider.port) as client:
            if provider.username is not None and provider.password is not None:
                client.authenticate(provider.username, provider.password)
            if group is not None:
                client.group(group)
    except NntpAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="NNTP provider authentication failed") from exc
    except NntpTemporaryError as exc:
        raise HTTPException(status_code=503, detail="NNTP provider is temporarily unavailable") from exc
    except NntpError as exc:
        raise HTTPException(status_code=502, detail="NNTP provider protocol test failed") from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="NNTP provider connection failed") from exc

    return ProviderTestResponse(status="ok", provider_id=provider.id, group=group)


@router.post("/{provider_id}/credentials/{field_name}/clear", response_model=ProviderResponse)
def clear_credential(provider_id: str, field_name: str, request: Request) -> ProviderResponse:
    if field_name not in {"username", "password"}:
        raise HTTPException(status_code=404, detail="Credential field not found")
    repo = _repo(request)
    try:
        return _masked(repo.update(provider_id, **{field_name: ProviderSecretUpdate.clear()}))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Provider not found") from exc


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: str, request: Request) -> Response:
    if not _repo(request).delete(provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    return Response(status_code=204)
