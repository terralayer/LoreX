from __future__ import annotations

from collections.abc import Iterator
import socket
import ssl
from typing import BinaryIO

from lorex.nntp.errors import (
    NntpArticleMissing,
    NntpAuthenticationError,
    NntpProtocolError,
    NntpTemporaryError,
)
from lorex.nntp.protocol import GroupInfo, OverviewRecord


class NntpClient:
    def __init__(
        self,
        host: str,
        port: int = 563,
        *,
        ssl_context: ssl.SSLContext | None = None,
        timeout: float = 30.0,
        max_line_length: int = 65_536,
        body_chunk_size: int = 65_536,
    ) -> None:
        if not host.strip():
            raise ValueError("host is required")
        if not 1 <= port <= 65_535:
            raise ValueError("port must be between 1 and 65535")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_line_length < 1024:
            raise ValueError("max_line_length is too small")
        if body_chunk_size <= 0:
            raise ValueError("body_chunk_size must be positive")
        self.host = host.strip()
        self.port = port
        self.timeout = timeout
        self.max_line_length = max_line_length
        self.body_chunk_size = body_chunk_size
        self.ssl_context = ssl_context or ssl.create_default_context()
        self._socket: ssl.SSLSocket | None = None
        self._reader: BinaryIO | None = None
        self._overview_command = "XOVER"

    def __enter__(self) -> "NntpClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        if self._socket is not None:
            return
        try:
            raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
            raw.settimeout(self.timeout)
            wrapped = self.ssl_context.wrap_socket(raw, server_hostname=self.host)
            wrapped.settimeout(self.timeout)
            self._socket = wrapped
            self._reader = wrapped.makefile("rb")
            code, _ = self._read_response()
            if code not in {200, 201}:
                self.close()
                raise NntpProtocolError("NNTP server rejected the connection")
        except NntpProtocolError:
            raise
        except (OSError, ssl.SSLError) as exc:
            self.close()
            raise NntpTemporaryError("NNTP connection failed") from exc

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._send_line("QUIT")
                self._read_response()
            except Exception:
                pass
        if self._reader is not None:
            try:
                self._reader.close()
            finally:
                self._reader = None
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None

    @staticmethod
    def _validate_argument(value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("NNTP command arguments cannot contain line breaks")
        return value

    def _send_line(self, command: str) -> None:
        if self._socket is None:
            raise NntpProtocolError("NNTP connection is not open")
        try:
            self._socket.sendall(command.encode("ascii") + b"\r\n")
        except (UnicodeEncodeError, OSError) as exc:
            raise NntpTemporaryError("NNTP command send failed") from exc

    def _read_raw_line(self) -> bytes:
        if self._reader is None:
            raise NntpProtocolError("NNTP connection is not open")
        try:
            line = self._reader.readline(self.max_line_length + 1)
        except OSError as exc:
            raise NntpTemporaryError("NNTP response read failed") from exc
        if not line:
            raise NntpTemporaryError("NNTP connection closed unexpectedly")
        if len(line) > self.max_line_length:
            raise NntpProtocolError("NNTP response line exceeds configured limit")
        if not line.endswith(b"\n"):
            raise NntpProtocolError("NNTP response line is incomplete")
        return line.rstrip(b"\r\n")

    def _read_response(self) -> tuple[int, str]:
        raw = self._read_raw_line()
        if len(raw) < 3 or not raw[:3].isdigit():
            raise NntpProtocolError("Malformed NNTP response")
        code = int(raw[:3])
        text = raw[4:].decode("utf-8", errors="replace") if len(raw) > 4 else ""
        return code, text

    @staticmethod
    def _raise_for_code(code: int, *, auth: bool = False, article: bool = False) -> None:
        if 200 <= code < 400:
            return
        if article and code in {423, 430}:
            raise NntpArticleMissing("NNTP article is unavailable")
        if auth and code in {480, 481, 482, 502}:
            raise NntpAuthenticationError("NNTP authentication failed")
        if 400 <= code < 500:
            raise NntpTemporaryError("NNTP provider returned a temporary failure")
        raise NntpProtocolError("NNTP provider rejected the command")

    def authenticate(self, username: str, password: str) -> None:
        username = self._validate_argument(username)
        password = self._validate_argument(password)
        self._send_line(f"AUTHINFO USER {username}")
        code, _ = self._read_response()
        if code == 281:
            return
        if code != 381:
            self._raise_for_code(code, auth=True)
            raise NntpAuthenticationError("NNTP authentication failed")
        self._send_line(f"AUTHINFO PASS {password}")
        code, _ = self._read_response()
        if code != 281:
            self._raise_for_code(code, auth=True)
            raise NntpAuthenticationError("NNTP authentication failed")

    def group(self, name: str) -> GroupInfo:
        name = self._validate_argument(name.strip())
        if not name:
            raise ValueError("group name is required")
        self._send_line(f"GROUP {name}")
        code, text = self._read_response()
        self._raise_for_code(code)
        if code != 211:
            raise NntpProtocolError("Unexpected GROUP response")
        parts = text.split()
        if len(parts) < 4:
            raise NntpProtocolError("Malformed GROUP response")
        try:
            return GroupInfo(count=int(parts[0]), low=int(parts[1]), high=int(parts[2]), name=parts[3])
        except ValueError as exc:
            raise NntpProtocolError("Malformed GROUP response") from exc

    def xover(self, start: int, end: int) -> Iterator[OverviewRecord]:
        if start < 0 or end < start:
            raise ValueError("invalid overview range")
        command = self._overview_command
        self._send_line(f"{command} {start}-{end}")
        code, _ = self._read_response()
        if command == "XOVER" and code in {500, 501, 502, 503}:
            self._overview_command = "OVER"
            self._send_line(f"OVER {start}-{end}")
            code, _ = self._read_response()
        self._raise_for_code(code)
        if code != 224:
            raise NntpProtocolError("Unexpected overview response")
        yield from self._read_overview_rows()

    def _read_overview_rows(self) -> Iterator[OverviewRecord]:
        while True:
            raw = self._read_raw_line()
            if raw == b".":
                return
            if raw.startswith(b".."):
                raw = raw[1:]
            fields = raw.decode("utf-8", errors="replace").split("\t")
            if len(fields) < 7:
                raise NntpProtocolError("Malformed overview row")
            try:
                yield OverviewRecord(
                    article_number=int(fields[0]),
                    subject=fields[1],
                    message_id=fields[4],
                    bytes=int(fields[6]),
                )
            except ValueError as exc:
                raise NntpProtocolError("Malformed overview row") from exc

    def body(self, message_id: str) -> Iterator[bytes]:
        message_id = self._validate_argument(message_id.strip())
        if not message_id:
            raise ValueError("message id is required")
        self._send_line(f"BODY {message_id}")
        code, _ = self._read_response()
        self._raise_for_code(code, article=True)
        if code != 222:
            raise NntpProtocolError("Unexpected BODY response")
        while True:
            raw = self._read_raw_line()
            if raw == b".":
                return
            if raw.startswith(b".."):
                raw = raw[1:]
            logical = raw + b"\r\n"
            for offset in range(0, len(logical), self.body_chunk_size):
                yield logical[offset : offset + self.body_chunk_size]
