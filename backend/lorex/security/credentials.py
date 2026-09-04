from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Mapping
from dataclasses import dataclass
import os
from secrets import token_bytes

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise CredentialError("invalid credential encoding")
    try:
        padding = "=" * (-len(value) % 4)
        return urlsafe_b64decode((value + padding).encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise CredentialError("invalid credential encoding") from exc


@dataclass(frozen=True, slots=True)
class CredentialCipher:
    _key: bytes

    @classmethod
    def from_base64url(cls, value: str) -> "CredentialCipher":
        key = _b64decode(value)
        if len(key) != 32:
            raise CredentialError("credential key must decode to exactly 32 bytes")
        return cls(key)

    @staticmethod
    def _aad(provider_id: str, field_name: str) -> bytes:
        if not provider_id or not field_name:
            raise CredentialError("provider id and field name are required")
        return f"lorex:nntp-provider:{provider_id}:{field_name}:v1".encode("utf-8")

    def encrypt(self, provider_id: str, field_name: str, plaintext: str) -> str:
        if not isinstance(plaintext, str):
            raise CredentialError("credential plaintext must be text")
        nonce = token_bytes(12)
        ciphertext = AESGCM(self._key).encrypt(
            nonce,
            plaintext.encode("utf-8"),
            self._aad(provider_id, field_name),
        )
        return f"v1.{_b64encode(nonce)}.{_b64encode(ciphertext)}"

    def decrypt(self, provider_id: str, field_name: str, envelope: str) -> str:
        try:
            version, nonce_text, ciphertext_text = envelope.split(".", 2)
        except (AttributeError, ValueError) as exc:
            raise CredentialError("invalid credential envelope") from exc
        if version != "v1":
            raise CredentialError("unsupported credential envelope version")
        nonce = _b64decode(nonce_text)
        ciphertext = _b64decode(ciphertext_text)
        if len(nonce) != 12:
            raise CredentialError("invalid credential envelope")
        try:
            plaintext = AESGCM(self._key).decrypt(
                nonce,
                ciphertext,
                self._aad(provider_id, field_name),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
            raise CredentialError("credential decryption failed") from exc


def credential_cipher_from_env(
    environ: Mapping[str, str] = os.environ,
) -> CredentialCipher | None:
    value = environ.get("LOREX_CREDENTIAL_KEY")
    if not value:
        return None
    return CredentialCipher.from_base64url(value)
