from __future__ import annotations

from collections.abc import Iterable, Iterator
import zlib

from lorex.nntp.errors import NntpProtocolError


def _parse_control(line: bytes) -> dict[bytes, bytes]:
    fields: dict[bytes, bytes] = {}
    for token in line.split()[1:]:
        key, separator, value = token.partition(b"=")
        if separator:
            fields[key] = value
    return fields


class StreamingYencDecoder:
    def __init__(self, *, output_chunk_size: int = 65_536, max_line_length: int = 65_536) -> None:
        if output_chunk_size <= 0:
            raise ValueError("output_chunk_size must be positive")
        if max_line_length < 1024:
            raise ValueError("max_line_length is too small")
        self.output_chunk_size = output_chunk_size
        self.max_line_length = max_line_length
        self._buffer = bytearray()
        self._output = bytearray()
        self._mode: str | None = None
        self._finished = False
        self._expected_size: int | None = None
        self._decoded_size = 0
        self._crc = 0

    def feed(self, chunk: bytes) -> Iterator[bytes]:
        if self._finished:
            if chunk:
                raise NntpProtocolError("Unexpected data after yEnc trailer")
            return
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("yEnc input chunks must be bytes-like")
        self._buffer.extend(chunk)
        if len(self._buffer) > self.max_line_length and b"\n" not in self._buffer:
            raise NntpProtocolError("yEnc line exceeds configured limit")

        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            raw = bytes(self._buffer[: newline + 1])
            del self._buffer[: newline + 1]
            yield from self._process_line(raw)

    def finish(self) -> Iterator[bytes]:
        if self._buffer:
            yield from self._process_line(bytes(self._buffer), terminal=True)
            self._buffer.clear()
        if self._mode == "yenc" and not self._finished:
            raise NntpProtocolError("Incomplete yEnc article")
        yield from self._flush_output(force=True)

    def _process_line(self, raw: bytes, *, terminal: bool = False) -> Iterator[bytes]:
        if len(raw) > self.max_line_length + 2:
            raise NntpProtocolError("yEnc line exceeds configured limit")
        logical = raw[:-2] if raw.endswith(b"\r\n") else raw[:-1] if raw.endswith(b"\n") else raw

        if self._mode is None:
            if logical.startswith(b"=ybegin "):
                self._mode = "yenc"
                fields = _parse_control(logical)
                try:
                    self._expected_size = int(fields[b"size"])
                except (KeyError, ValueError) as exc:
                    raise NntpProtocolError("Malformed yEnc header") from exc
                return
            self._mode = "plain"

        if self._mode == "plain":
            self._output.extend(raw)
            yield from self._flush_output()
            return

        if logical.startswith(b"=ypart "):
            return
        if logical.startswith(b"=yend "):
            fields = _parse_control(logical)
            try:
                trailer_size = int(fields[b"size"])
            except (KeyError, ValueError) as exc:
                raise NntpProtocolError("Malformed yEnc trailer") from exc
            if trailer_size != self._decoded_size:
                raise NntpProtocolError("yEnc decoded size mismatch")
            if self._expected_size is not None and trailer_size > self._expected_size:
                raise NntpProtocolError("yEnc decoded size exceeds declared size")
            checksum = fields.get(b"pcrc32") or fields.get(b"crc32")
            if checksum is not None:
                try:
                    expected_crc = int(checksum, 16)
                except ValueError as exc:
                    raise NntpProtocolError("Malformed yEnc checksum") from exc
                if expected_crc != self._crc & 0xFFFFFFFF:
                    raise NntpProtocolError("yEnc checksum mismatch")
            self._finished = True
            yield from self._flush_output(force=True)
            return

        decoded = bytearray()
        escaped = False
        for value in logical:
            if escaped:
                encoded = (value - 64) & 0xFF
                decoded.append((encoded - 42) & 0xFF)
                escaped = False
            elif value == 61:
                escaped = True
            else:
                decoded.append((value - 42) & 0xFF)
        if escaped:
            raise NntpProtocolError("Incomplete yEnc escape sequence")
        self._decoded_size += len(decoded)
        self._crc = zlib.crc32(decoded, self._crc)
        self._output.extend(decoded)
        yield from self._flush_output()

    def _flush_output(self, *, force: bool = False) -> Iterator[bytes]:
        while len(self._output) >= self.output_chunk_size:
            chunk = bytes(self._output[: self.output_chunk_size])
            del self._output[: self.output_chunk_size]
            yield chunk
        if force and self._output:
            chunk = bytes(self._output)
            self._output.clear()
            yield chunk


def decode_yenc_stream(
    chunks: Iterable[bytes],
    *,
    output_chunk_size: int = 65_536,
    max_line_length: int = 65_536,
) -> Iterator[bytes]:
    decoder = StreamingYencDecoder(
        output_chunk_size=output_chunk_size,
        max_line_length=max_line_length,
    )
    for chunk in chunks:
        yield from decoder.feed(chunk)
    yield from decoder.finish()
