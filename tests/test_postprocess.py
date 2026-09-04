from __future__ import annotations

from pathlib import Path

import pytest

from lorex.domain import DownloadResult
from lorex.postprocess import PostProcessError, PostProcessor


def _result(tmp_path: Path, paths: tuple[Path, ...], subjects: tuple[str, ...], *, format: str = "m4b") -> DownloadResult:
    return DownloadResult(
        release_id="release-1",
        title="Synthetic Book",
        author="Synthetic Author",
        narrator=None,
        format=format,
        file_name=f"Synthetic Book.{format}",
        size=sum(path.stat().st_size for path in paths),
        staging_dir=str(tmp_path),
        article_paths=tuple(str(path) for path in paths),
        article_subjects=subjects,
    )


def test_postprocessor_reassembles_multipart_direct_audio_in_order(tmp_path: Path) -> None:
    first = tmp_path / "part-1"
    second = tmp_path / "part-2"
    first.write_bytes(b"first-")
    second.write_bytes(b"second")

    processed = PostProcessor().process(
        _result(
            tmp_path,
            (first, second),
            (
                '"Synthetic Book.m4b" yEnc [1/2]',
                '"Synthetic Book.m4b" yEnc [2/2]',
            ),
        )
    )

    assert processed.path.is_file()
    assert processed.path.suffix.lower() == ".m4b"
    assert processed.path.read_bytes() == b"first-second"
    assert processed.size == len(b"first-second")


def test_postprocessor_uses_par2_and_7z_for_archive_payload(tmp_path: Path) -> None:
    par2 = tmp_path / "par2-part"
    archive = tmp_path / "rar-part"
    par2.write_bytes(b"PAR2\x00PKT" + b"p" * 16)
    archive.write_bytes(b"Rar!\x1a\x07\x00" + b"r" * 16)
    commands: list[list[str]] = []

    def runner(args: list[str], cwd: Path) -> None:
        commands.append(args)
        if args[0] == "7z":
            output_arg = next(item for item in args if item.startswith("-o"))
            output_dir = Path(output_arg[2:])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "Synthetic Book.m4b").write_bytes(b"audio")

    processed = PostProcessor(command_runner=runner).process(
        _result(
            tmp_path,
            (par2, archive),
            ('"Synthetic Book.par2" yEnc [1/1]', '"Synthetic Book.rar" yEnc [1/1]'),
        )
    )

    assert any(command[0] == "par2" for command in commands)
    assert any(command[0] == "7z" for command in commands)
    assert processed.path.read_bytes() == b"audio"


def test_postprocessor_fails_closed_when_no_supported_audio_is_produced(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    payload.write_bytes(b"not-audio")

    with pytest.raises(PostProcessError, match="supported audiobook"):
        PostProcessor().process(
            _result(tmp_path, (payload,), ('"notes.txt" yEnc [1/1]',), format="mp3")
        )
