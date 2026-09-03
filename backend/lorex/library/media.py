from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MediaAction(str, Enum):
    PRESERVE = "preserve"
    REMUX = "remux"
    TRANSCODE = "transcode"


@dataclass(frozen=True, slots=True)
class MediaProbe:
    container: str
    audio_codec: str
    valid: bool
    duration_seconds: float | None = None


def choose_media_action(probe: MediaProbe) -> MediaAction:
    if not probe.valid:
        return MediaAction.TRANSCODE
    containers = {part.strip().casefold() for part in probe.container.split(",")}
    codec = probe.audio_codec.casefold()
    if "mov" in containers or "mp4" in containers or "m4a" in containers:
        if codec in {"aac", "alac"}:
            return MediaAction.PRESERVE
    if codec in {"aac", "alac"}:
        return MediaAction.REMUX
    return MediaAction.TRANSCODE
