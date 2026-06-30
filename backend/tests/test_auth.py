"""
ESGenuine — auth unit tests (offline: pure bcrypt + JWT, no DB / network).
Locks the token + password primitives and the get_current_user gate behavior.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from api import auth  # noqa: E402


def _req(authorization=None):
    headers = {}
    if authorization is not None:
        headers["Authorization"] = authorization
    return SimpleNamespace(headers=headers)


def test_password_hash_roundtrip():
    h = auth.hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert auth.verify_password("correct horse battery staple", h)
    assert not auth.verify_password("wrong", h)
    assert not auth.verify_password("x", "not-a-bcrypt-hash")  # malformed hash → False, no crash


def test_access_token_roundtrip():
    tok = auth.create_access_token("a@b.com", role="admin")
    payload = auth.decode_token(tok, expected_type="access")
    assert payload["sub"] == "a@b.com" and payload["role"] == "admin" and payload["type"] == "access"


def test_token_type_is_enforced():
    access = auth.create_access_token("a@b.com")
    refresh = auth.create_refresh_token("a@b.com")
    with pytest.raises(Exception):   # access decoded as refresh → 401
        auth.decode_token(access, expected_type="refresh")
    with pytest.raises(Exception):   # refresh decoded as access → 401
        auth.decode_token(refresh, expected_type="access")
    # right types decode fine
    assert auth.decode_token(refresh, expected_type="refresh")["sub"] == "a@b.com"


def test_expired_token_rejected():
    expired = jwt.encode(
        {"sub": "a@b.com", "role": "user", "type": "access",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        auth.SECRET_KEY, algorithm=auth.ALGORITHM,
    )
    with pytest.raises(Exception):
        auth.decode_token(expired, expected_type="access")


def test_garbage_token_rejected():
    with pytest.raises(Exception):
        auth.decode_token("not.a.jwt", expected_type="access")


def test_get_current_user_requires_bearer():
    # valid bearer → user dict
    tok = auth.create_access_token("u@b.com", role="user")
    user = auth.get_current_user(_req(f"Bearer {tok}"))
    assert user == {"email": "u@b.com", "role": "user"}
    # missing header → 401
    with pytest.raises(Exception):
        auth.get_current_user(_req(None))
    # non-bearer scheme → 401
    with pytest.raises(Exception):
        auth.get_current_user(_req("Basic abc"))


def test_require_role():
    admin = {"email": "a@b.com", "role": "admin"}
    user = {"email": "u@b.com", "role": "user"}
    dep = auth.require_role("admin")
    assert dep(admin) == admin
    with pytest.raises(Exception):
        dep(user)


_ALL_TESTS = [
    test_password_hash_roundtrip, test_access_token_roundtrip, test_token_type_is_enforced,
    test_expired_token_rejected, test_garbage_token_rejected, test_get_current_user_requires_bearer,
    test_require_role,
]

if __name__ == "__main__":
    for t in _ALL_TESTS:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(_ALL_TESTS)}/{len(_ALL_TESTS)} passed")
