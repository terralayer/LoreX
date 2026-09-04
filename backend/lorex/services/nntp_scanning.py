from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from lorex.nntp.models import NntpProvider, NntpProviderGroup
from lorex.nntp.scanner import ScanStats, scan_group_once

ScanMode = Literal["live", "backfill"]


def scan_provider_group_once(
    provider: NntpProvider,
    group: NntpProviderGroup,
    release_repository,
    *,
    client_factory: Callable | None = None,
    mode: ScanMode = "live",
) -> ScanStats:
    kwargs = {"mode": mode}
    if client_factory is not None:
        kwargs["client_factory"] = client_factory
    return scan_group_once(provider, group, release_repository, **kwargs)
