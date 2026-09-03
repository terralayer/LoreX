from __future__ import annotations

import errno
from pathlib import Path

import pytest

from lorex.library.filesystem import promote_verified_file


def test_promotion_replaces_destination_and_removes_source_only_after_verification(tmp_path: Path) -> None:
    source = tmp_path / "source.m4b"
    destination = tmp_path / "library" / "book.m4b"
    source.write_bytes(b"audio")
    seen = []

    size = promote_verified_file(source, destination, lambda path: seen.append(path) or True)

    assert size == 5
    assert destination.read_bytes() == b"audio"
    assert not source.exists()
    assert seen == [destination]


def test_failed_verification_keeps_source(tmp_path: Path) -> None:
    source = tmp_path / "source.m4b"
    destination = tmp_path / "library" / "book.m4b"
    source.write_bytes(b"audio")

    with pytest.raises(ValueError):
        promote_verified_file(source, destination, lambda _path: False)

    assert source.exists()
    assert not destination.exists()
