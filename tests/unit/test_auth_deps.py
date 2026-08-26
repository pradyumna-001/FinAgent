from datetime import datetime, timedelta, UTC

import pytest
from jose import jwt

from app.api.errors import InvalidTokenError

from app.core.security import (
    create_access_token,
    decode_access_token,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.core.config import settings


def test_create_access_token_returns_string() -> None:
    """create_access_token returns a non-empty string (JWT)."""
    result = create_access_token({"sub": "1"})

    assert len(result) > 0
    assert isinstance(result, str)


def test_create_access_token_includes_exp_claim() -> None:
    """Token payload contains 'exp' claim (expiration timestamp)."""
    token = create_access_token({"sub": "1", "email": "test@example.com"})
    payload = jwt.decode(token, key="", options={"verify_signature": False})

    assert "exp" in payload
    assert isinstance(payload["exp"], int)
    

def test_create_access_token_custom_expires_delta() -> None:
    """Custom expires_delta overrides default ACCESS_TOKEN_EXPIRE_MINUTES."""
    token = create_access_token({"sub": "1"}, expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, key="", options={"verify_signature": False})

    now = datetime.now(UTC)
    expected_exp = now + timedelta(minutes=5)
    assert abs(payload["exp"] - expected_exp.timestamp()) < 10
     

def test_decode_access_token_valid_returns_payload() -> None:
    """Valid token decoded successfully, returns payload dict."""
    token = create_access_token({"sub": "1", "email": "test@example.com"}, expires_delta=timedelta(minutes=5))
    res = decode_access_token(token)

    assert isinstance(res, dict)
    assert res["sub"] == "1"
    assert res["email"] == "test@example.com"
    assert "sub" in res
    assert "exp" in res


def test_decode_access_token_expired_raises() -> None:
    """Expired token raises JWTError (or custom InvalidTokenError)."""
    token = create_access_token({"sub": "1", "email": "test@example.com"}, expires_delta=timedelta(minutes=-10))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_access_token_invalid_signature_raises() -> None:
    """Token signed with different secret raises JWTError."""
    to_encode = {"sub": "1", "email": "test@example.com"}
    token = jwt.encode(to_encode, "wrong-secret", algorithm=ALGORITHM)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)
    

def test_decode_access_token_malformed_raises() -> None:
    """Malformed token string (not a valid JWT) raises JWTError."""
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.valid.token")    


def test_algorithm_constant_is_hs256() -> None:
    """ALGORITHM constant matches expected HS256."""
    assert ALGORITHM == "HS256"


def test_access_token_expire_minutes_default_30() -> None:
    """ACCESS_TOKEN_EXPIRE_MINUTES default is 30."""
    assert ACCESS_TOKEN_EXPIRE_MINUTES == 30


def test_secret_key_from_settings() -> None:
    """SECRET_KEY is loaded from settings (non-empty in test env)."""
    assert settings.SECRET_KEY
    assert len(settings.SECRET_KEY) > 0