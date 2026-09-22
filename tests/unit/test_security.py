from aigateway.auth.security import (
    api_key_prefix,
    decode_access_token,
    hash_secret,
    mint_access_token,
    new_api_key,
    new_refresh_secret,
    parse_bearer,
    verify_secret,
)
from aigateway.config import AuthSettings


def test_hash_and_verify_secret() -> None:
    hashed = hash_secret("changeme")
    assert hashed != "changeme"
    assert verify_secret(hashed, "changeme") is True
    assert verify_secret(hashed, "wrong") is False


def test_api_key_prefix_length() -> None:
    key = new_api_key()
    assert key.startswith("agt_")
    assert len(api_key_prefix(key)) == 16


def test_parse_bearer() -> None:
    assert parse_bearer("Bearer abc") == "abc"
    assert parse_bearer("basic abc") is None
    assert parse_bearer(None) is None


def test_access_token_roundtrip() -> None:
    settings = AuthSettings(
        postgres_dsn="postgresql://x",
        jwt_secret="unit-test-secret",
        internal_auth_token="tok",
    )
    token = mint_access_token(settings, user_id="u1", tenant_id="t1", role="app_user")
    payload = decode_access_token(settings, token)
    assert payload["sub"] == "u1"
    assert payload["tenant_id"] == "t1"
    assert payload["typ"] == "access"


def test_refresh_token_format() -> None:
    token_id, plain = new_refresh_secret()
    assert str(token_id) in plain
    assert "." in plain
