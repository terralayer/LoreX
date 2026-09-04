from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
import socketserver
import ssl
import tempfile
from threading import Thread

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server: FakeNntpServer = self.server.fake_owner  # type: ignore[attr-defined]
        self.wfile.write(b"200 fake-nntp ready\r\n")
        authenticated = False
        while True:
            raw = self.rfile.readline(65537)
            if not raw:
                return
            command = raw.decode("ascii").rstrip("\r\n")
            server.commands.append(command)
            verb, _, arg = command.partition(" ")
            verb = verb.upper()
            if verb == "AUTHINFO" and arg.startswith("USER "):
                self.wfile.write(b"381 password required\r\n")
            elif verb == "AUTHINFO" and arg.startswith("PASS "):
                if server.auth_ok:
                    authenticated = True
                    self.wfile.write(b"281 authentication accepted\r\n")
                else:
                    self.wfile.write(b"481 authentication rejected\r\n")
            elif verb == "GROUP":
                if server.require_auth and not authenticated:
                    self.wfile.write(b"480 authentication required\r\n")
                else:
                    self.wfile.write(f"211 {server.high - server.low + 1} {server.low} {server.high} {arg}\r\n".encode())
            elif verb in {"XOVER", "OVER"}:
                if verb == "XOVER" and not server.support_xover:
                    self.wfile.write(b"500 XOVER unsupported\r\n")
                    continue
                self.wfile.write(b"224 overview follows\r\n")
                for row in server.overview_rows:
                    self.wfile.write(row.encode("utf-8") + b"\r\n")
                self.wfile.write(b".\r\n")
            elif verb == "BODY":
                payload = server.bodies.get(arg)
                if payload is None:
                    self.wfile.write(b"430 no such article\r\n")
                    continue
                self.wfile.write(b"222 body follows\r\n")
                for line in payload.splitlines():
                    if line.startswith(b"."):
                        line = b"." + line
                    self.wfile.write(line + b"\r\n")
                self.wfile.write(b".\r\n")
            elif verb == "QUIT":
                self.wfile.write(b"205 closing connection\r\n")
                return
            else:
                self.wfile.write(b"500 unknown command\r\n")


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class FakeNntpServer(AbstractContextManager["FakeNntpServer"]):
    def __init__(self) -> None:
        self.low = 100
        self.high = 200
        self.auth_ok = True
        self.require_auth = True
        self.support_xover = True
        self.overview_rows = [
            '101\tAuthor - Book.m4b (1/1)\tposter\tdate\t<101@test>\t\t1234\t10'
        ]
        self.bodies: dict[str, bytes] = {"<101@test>": b"first\n.second\nthird"}
        self.commands: list[str] = []
        self._tmp = tempfile.TemporaryDirectory()
        self._server: _Server | None = None
        self._thread: Thread | None = None
        self.client_context: ssl.SSLContext | None = None

    def __enter__(self) -> "FakeNntpServer":
        root = Path(self._tmp.name)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ip_address("127.0.0.1"))]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        cert_path = root / "cert.pem"
        key_path = root / "key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert_path, key_path)
        self.client_context = ssl.create_default_context(cafile=str(cert_path))
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.fake_owner = self  # type: ignore[attr-defined]
        self._server.socket = server_context.wrap_socket(self._server.socket, server_side=True)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def port(self) -> int:
        assert self._server is not None
        return int(self._server.server_address[1])

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._tmp.cleanup()
