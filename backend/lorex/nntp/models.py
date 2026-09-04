from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True, slots=True)
class NntpProviderGroup:
    group_name: str
    enabled: bool = True
    scan_batch_size: int = 5000
    backfill_days: int = 0

    def __post_init__(self) -> None:
        cleaned = self.group_name.strip()
        if not cleaned:
            raise ValueError("group name must not be empty")
        if not 100 <= self.scan_batch_size <= 50_000:
            raise ValueError("scan_batch_size must be between 100 and 50000")
        if not 0 <= self.backfill_days <= 10_000:
            raise ValueError("backfill_days must be between 0 and 10000")
        object.__setattr__(self, "group_name", cleaned)

    @property
    def normalized_name(self) -> str:
        return self.group_name.casefold()


@dataclass(frozen=True, slots=True)
class NntpProvider:
    id: str
    name: str
    host: str
    port: int = 563
    enabled: bool = True
    priority: int = 100
    fill_server: bool = False
    max_connections: int = 4
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)
    groups: tuple[NntpProviderGroup, ...] = ()


@dataclass(frozen=True, slots=True)
class NntpProviderSummary:
    id: str
    name: str
    host: str
    port: int = 563
    enabled: bool = True
    priority: int = 100
    fill_server: bool = False
    max_connections: int = 4
    username_configured: bool = False
    password_configured: bool = False
    groups: tuple[NntpProviderGroup, ...] = ()


class _SecretAction(str, Enum):
    KEEP = "keep"
    CLEAR = "clear"
    REPLACE = "replace"


@dataclass(frozen=True, slots=True)
class ProviderSecretUpdate:
    action: _SecretAction
    value: str | None = field(default=None, repr=False)

    @classmethod
    def keep(cls) -> "ProviderSecretUpdate":
        return cls(_SecretAction.KEEP)

    @classmethod
    def clear(cls) -> "ProviderSecretUpdate":
        return cls(_SecretAction.CLEAR)

    @classmethod
    def replace(cls, value: str) -> "ProviderSecretUpdate":
        if not isinstance(value, str):
            raise ValueError("credential value must be text")
        return cls(_SecretAction.REPLACE, value)

    @property
    def is_keep(self) -> bool:
        return self.action is _SecretAction.KEEP

    @property
    def is_clear(self) -> bool:
        return self.action is _SecretAction.CLEAR

    @property
    def is_replace(self) -> bool:
        return self.action is _SecretAction.REPLACE
