from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any


def collect_frontend_size(dist: str | Path) -> dict[str, Any]:
    root = Path(dist)
    if not root.is_dir():
        raise FileNotFoundError(root)

    files: list[dict[str, int | str]] = []
    raw_total = 0
    gzip_total = 0
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        data = path.read_bytes()
        compressed = gzip.compress(data, compresslevel=9, mtime=0)
        raw_bytes = len(data)
        gzip_bytes = len(compressed)
        raw_total += raw_bytes
        gzip_total += gzip_bytes
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "raw_bytes": raw_bytes,
                "gzip_bytes": gzip_bytes,
            }
        )

    return {
        "file_count": len(files),
        "raw_bytes": raw_total,
        "gzip_bytes": gzip_total,
        "files": files,
    }
