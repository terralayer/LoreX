from __future__ import annotations

import re
import shutil
import subprocess
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lorex.domain import DownloadResult

_AUDIO_EXTENSIONS = {".m4b", ".m4a", ".mp3", ".aac", ".flac"}
_ARCHIVE_EXTENSIONS = {".rar", ".7z", ".zip"}
_INTERESTING_FILENAME = re.compile(
    r"(?P<name>[^\"'<>/\\]+\.(?:m4b|m4a|mp3|aac|flac|par2|rar|r\d{2}|7z|zip))",
    re.IGNORECASE,
)
_QUOTED_FILENAME = re.compile(
    r"[\"'](?P<name>[^\"'<>/\\]+\.(?:m4b|m4a|mp3|aac|flac|par2|rar|r\d{2}|7z|zip))[\"']",
    re.IGNORECASE,
)
_ANY_FILENAME = re.compile(
    r"(?:[\"'](?P<quoted>[^\"'<>/\\]+\.[A-Za-z0-9]{1,12})[\"']|(?P<plain>[^\s\"'<>/\\]+\.[A-Za-z0-9]{1,12}))"
)


class PostProcessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessedAudiobook:
    path: Path
    format: str
    size: int


def _safe_name(value: str) -> str:
    return Path(value.replace("\\", "/")).name.strip().strip(".") or "payload.bin"


def _filename_from_subject(subject: str) -> str | None:
    match = _QUOTED_FILENAME.search(subject) or _INTERESTING_FILENAME.search(subject)
    if match is None:
        return None
    return _safe_name(match.group("name").strip())


def _subject_has_explicit_filename(subject: str) -> bool:
    return _ANY_FILENAME.search(subject) is not None


def _magic_extension(path: Path) -> str | None:
    with path.open("rb") as handle:
        prefix = handle.read(16)
    if prefix.startswith(b"PAR2\x00PKT"):
        return ".par2"
    if prefix.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")):
        return ".rar"
    if prefix.startswith(b"7z\xbc\xaf'\x1c"):
        return ".7z"
    if prefix.startswith(b"PK\x03\x04"):
        return ".zip"
    return None


def _copy_join(parts: list[Path], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    temporary.unlink(missing_ok=True)
    with temporary.open("wb") as output:
        for part in parts:
            with part.open("rb") as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    temporary.replace(destination)
    return destination


def _default_command_runner(args: list[str], cwd: Path) -> None:
    try:
        subprocess.run(
            args,
            cwd=str(cwd),
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=3600,
        )
    except FileNotFoundError as exc:
        raise PostProcessError(f"Required post-processing tool is unavailable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PostProcessError(f"Post-processing command timed out: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()[-1000:]
        raise PostProcessError(f"Post-processing command failed: {args[0]}{': ' + detail if detail else ''}") from exc


class PostProcessor:
    def __init__(self, *, command_runner: Callable[[list[str], Path], None] | None = None) -> None:
        self._run = command_runner or _default_command_runner

    def process(self, result: DownloadResult) -> ProcessedAudiobook:
        if not result.staging_dir:
            raise PostProcessError("Download did not provide a staging directory")
        if not result.article_paths:
            raise PostProcessError("Download did not produce article files")

        staging = Path(result.staging_dir).resolve()
        paths = tuple(Path(value).resolve() for value in result.article_paths)
        for path in paths:
            if not path.is_file():
                raise PostProcessError(f"Downloaded article file is missing: {path.name}")
            if not path.is_relative_to(staging):
                raise PostProcessError("Downloaded article escaped the job staging directory")

        work = staging / "postprocessed"
        reconstructed = work / "reconstructed"
        extracted = work / "extracted"
        if work.exists():
            shutil.rmtree(work)
        reconstructed.mkdir(parents=True)

        subjects = result.article_subjects
        if len(subjects) != len(paths):
            subjects = tuple("" for _ in paths)

        grouped: OrderedDict[str, list[Path]] = OrderedDict()
        unnamed: list[Path] = []
        for path, subject in zip(paths, subjects, strict=True):
            name = _filename_from_subject(subject)
            if name is None:
                unnamed.append(path)
            else:
                grouped.setdefault(name, []).append(path)

        if unnamed:
            if grouped:
                for index, path in enumerate(unnamed, 1):
                    extension = _magic_extension(path) or ".bin"
                    grouped[f"unnamed-{index:04d}{extension}"] = [path]
            else:
                detected = _magic_extension(unnamed[0])
                explicit_unsupported_name = detected is None and any(
                    _subject_has_explicit_filename(subject) for subject in subjects
                )
                if explicit_unsupported_name:
                    fallback = "payload.bin"
                else:
                    extension = detected or f".{result.format.lower()}"
                    fallback = _safe_name(result.file_name)
                    if Path(fallback).suffix.lower() not in _AUDIO_EXTENSIONS | _ARCHIVE_EXTENSIONS | {".par2"}:
                        fallback = f"payload{extension}"
                grouped[fallback] = unnamed

        reconstructed_paths: list[Path] = []
        for name, parts in grouped.items():
            destination = reconstructed / _safe_name(name)
            reconstructed_paths.append(_copy_join(parts, destination))

        normalized_paths: list[Path] = []
        for index, path in enumerate(reconstructed_paths, 1):
            detected = _magic_extension(path)
            if detected is not None and path.suffix.lower() != detected:
                renamed = path.with_name(f"payload-{index:04d}{detected}")
                path.replace(renamed)
                path = renamed
            normalized_paths.append(path)
        reconstructed_paths = normalized_paths

        par2_files = [path for path in reconstructed_paths if path.suffix.lower() == ".par2"]
        for par2_file in par2_files:
            self._run(["par2", "r", str(par2_file)], reconstructed)

        archives = [path for path in reconstructed_paths if path.suffix.lower() in _ARCHIVE_EXTENSIONS]
        audio_roots = [reconstructed]
        if archives:
            extracted.mkdir(parents=True, exist_ok=True)
            primary = self._primary_archive(archives)
            if primary.suffix.lower() == ".rar":
                self._run(
                    [
                        "unar",
                        "-force-overwrite",
                        "-output-directory",
                        str(extracted),
                        str(primary),
                    ],
                    reconstructed,
                )
            else:
                self._run(["7z", "x", "-y", f"-o{extracted}", str(primary)], reconstructed)
            audio_roots.insert(0, extracted)

        audio_files = self._audio_files(audio_roots)
        if not audio_files:
            raise PostProcessError("Post-processing produced no supported audiobook file")

        if len(audio_files) > 1:
            extensions = {path.suffix.lower() for path in audio_files}
            if extensions == {".mp3"}:
                combined = work / "combined.mp3"
                _copy_join(sorted(audio_files, key=lambda path: path.name.casefold()), combined)
                audio_files = [combined]
            else:
                raise PostProcessError("Post-processing produced multiple audiobook files that cannot be safely combined")

        final = audio_files[0]
        return ProcessedAudiobook(path=final, format=final.suffix.lower().lstrip("."), size=final.stat().st_size)

    @staticmethod
    def _primary_archive(archives: list[Path]) -> Path:
        def rank(path: Path) -> tuple[int, str]:
            name = path.name.casefold()
            if name.endswith(".rar") and not re.search(r"\.part\d+\.rar$", name):
                priority = 0
            elif re.search(r"\.part0*1\.rar$", name):
                priority = 1
            elif name.endswith(".7z"):
                priority = 2
            elif name.endswith(".zip"):
                priority = 3
            else:
                priority = 4
            return priority, name

        return sorted(archives, key=rank)[0]

    @staticmethod
    def _audio_files(roots: list[Path]) -> list[Path]:
        seen: set[Path] = set()
        files: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            resolved_root = root.resolve()
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in _AUDIO_EXTENSIONS:
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(resolved_root):
                    continue
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(resolved)
        return files
