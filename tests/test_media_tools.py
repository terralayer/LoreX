from __future__ import annotations

import pytest

from lorex.library.tools import MediaWorkerLimits


def test_media_worker_limits_are_positive() -> None:
    limits = MediaWorkerLimits(repair=1, extraction=2, ffmpeg=3)
    assert (limits.repair, limits.extraction, limits.ffmpeg) == (1, 2, 3)


@pytest.mark.parametrize("field", ["repair", "extraction", "ffmpeg"])
def test_media_worker_limits_reject_zero(field: str) -> None:
    values = {"repair": 1, "extraction": 1, "ffmpeg": 1}
    values[field] = 0
    with pytest.raises(ValueError):
        MediaWorkerLimits(**values)
