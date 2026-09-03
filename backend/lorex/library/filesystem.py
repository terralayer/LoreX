from __future__ import annotations

import errno
import os
from pathlib import Path
import shutil
from collections.abc import Callable


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def promote_verified_file(source: Path, destination: Path, verifier: Callable[[Path], bool]) -> int:
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = source.stat().st_size
    try:
        os.replace(source, destination)
        moved = True
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        moved = False
        temporary = destination.with_name(f".{destination.name}.importing")
        temporary.unlink(missing_ok=True)
        with source.open("rb") as src, temporary.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        if not verifier(temporary):
            temporary.unlink(missing_ok=True)
            raise ValueError("promoted file failed verification")
        os.replace(temporary, destination)
        _fsync_file(destination)
        source.unlink()
        return size

    if not verifier(destination):
        if moved:
            os.replace(destination, source)
        raise ValueError("promoted file failed verification")
    _fsync_file(destination)
    return size
