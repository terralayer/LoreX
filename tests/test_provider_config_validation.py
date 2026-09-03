from __future__ import annotations

import pytest

from lorex.downloader.provider import ProviderConfig


def test_provider_config_rejects_nonpositive_connection_count() -> None:
    with pytest.raises(ValueError, match="max_connections"):
        ProviderConfig("primary", "primary.example", max_connections=0)
