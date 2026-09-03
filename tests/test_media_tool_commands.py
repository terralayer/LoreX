from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

from lorex.library.tools import MediaWorkerLimits, ToolRunner


class CapturingRunner(ToolRunner):
    def __init__(self) -> None:
        super().__init__(MediaWorkerLimits())
        self.commands: list[list[str]] = []

    def _execute(self, command, gate):
        self.commands.append(list(command))
        return CompletedProcess(command, 0, stdout='{}', stderr='')


def test_par2_repair_uses_repair_gate_and_safe_argv(tmp_path: Path) -> None:
    runner = CapturingRunner()
    runner.par2_repair(tmp_path / "book.par2")
    assert runner.commands == [["par2", "repair", str(tmp_path / "book.par2")]]


def test_ffprobe_requests_json_without_shell(tmp_path: Path) -> None:
    runner = CapturingRunner()
    runner.ffprobe(tmp_path / "book.m4b")
    assert runner.commands[0][:4] == ["ffprobe", "-v", "error", "-of"]
    assert runner.commands[0][-1] == str(tmp_path / "book.m4b")


def test_remux_uses_stream_copy_and_transcode_is_explicit(tmp_path: Path) -> None:
    runner = CapturingRunner()
    source = tmp_path / "source.mka"
    target = tmp_path / "target.m4b"
    runner.ffmpeg_remux(source, target)
    assert "copy" in runner.commands[0]
    runner.ffmpeg_transcode(source, target)
    assert "aac" in runner.commands[1]


def test_extraction_is_bounded_and_targeted_to_directory(tmp_path: Path) -> None:
    runner = CapturingRunner()
    archive = tmp_path / "book.7z"
    target = tmp_path / "extract"
    runner.extract_7z(archive, target)
    assert runner.commands == [["7z", "x", "-y", f"-o{target}", str(archive)]]
