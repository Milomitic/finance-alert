"""Tests for password and session token primitives."""
import pytest

from app.core import security


def test_hash_and_verify_password() -> None:
    pw = "correct horse battery staple"
    h = security.hash_password(pw)
    assert security.verify_password(pw, h) is True
    assert security.verify_password("wrong", h) is False


def test_session_token_roundtrip() -> None:
    token = security.create_session_token("admin")
    assert security.read_session_token(token) == "admin"


def test_session_token_tampered_returns_none() -> None:
    token = security.create_session_token("admin")
    bad = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    assert security.read_session_token(bad) is None


def test_session_token_expired() -> None:
    token = security.create_session_token("admin")
    with pytest.raises(ValueError):
        security.read_session_token(token, max_age_seconds=-1)
