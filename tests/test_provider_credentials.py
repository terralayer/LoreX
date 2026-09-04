from base64 import urlsafe_b64encode

import pytest

from lorex.security.credentials import CredentialCipher, CredentialError, credential_cipher_from_env


def _key(byte: int = 7) -> str:
    return urlsafe_b64encode(bytes([byte]) * 32).decode().rstrip("=")


def test_envelope_is_not_plaintext_and_round_trips():
    cipher = CredentialCipher.from_base64url(_key())
    value = cipher.encrypt("provider-1", "password", "secret-pass")
    assert "secret-pass" not in value
    assert value.startswith("v1.")
    assert cipher.decrypt("provider-1", "password", value) == "secret-pass"


def test_wrong_provider_aad_fails_closed():
    cipher = CredentialCipher.from_base64url(_key())
    value = cipher.encrypt("provider-1", "password", "secret-pass")
    with pytest.raises(CredentialError):
        cipher.decrypt("provider-2", "password", value)


def test_wrong_field_aad_fails_closed():
    cipher = CredentialCipher.from_base64url(_key())
    value = cipher.encrypt("provider-1", "password", "secret-pass")
    with pytest.raises(CredentialError):
        cipher.decrypt("provider-1", "username", value)


def test_wrong_key_fails_closed():
    value = CredentialCipher.from_base64url(_key(7)).encrypt("p", "username", "user")
    with pytest.raises(CredentialError):
        CredentialCipher.from_base64url(_key(8)).decrypt("p", "username", value)


def test_missing_environment_key_is_none():
    assert credential_cipher_from_env({}) is None


def test_valid_environment_key_builds_cipher():
    cipher = credential_cipher_from_env({"LOREX_CREDENTIAL_KEY": _key()})
    assert cipher is not None
    value = cipher.encrypt("provider-1", "username", "alice")
    assert cipher.decrypt("provider-1", "username", value) == "alice"


@pytest.mark.parametrize("value", ["not-base64!", urlsafe_b64encode(b"short").decode().rstrip("=")])
def test_invalid_environment_key_fails_closed(value: str):
    with pytest.raises(CredentialError):
        credential_cipher_from_env({"LOREX_CREDENTIAL_KEY": value})
