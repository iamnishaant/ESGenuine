"""
ESGenuine — Bearer-token auth (gates the write endpoints).

Adapted from the Clarity-Stack auth core (bcrypt + HS256 JWT access/refresh + RBAC),
trimmed for ESGenuine's cross-origin SPA→API setup: Bearer header only, no httpOnly
cookies / CSRF (those are for same-origin browser apps; here the SPA calls a separate
API origin and sends `Authorization: Bearer <jwt>`).

  register/login  →  {access_token, refresh_token}
  protected route →  user = Depends(get_current_user)   # 401 if no/invalid token
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Request

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

# JWT_SECRET signs the tokens. Fail-closed in production; in dev/CI (no secret set) fall
# back to an ephemeral random secret so tests run — tokens just won't survive a restart.
_IS_PROD = os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod")
SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    if _IS_PROD:
        raise RuntimeError(
            "JWT_SECRET must be set in production. Generate one with: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    SECRET_KEY = secrets.token_hex(32)
    print("[auth] WARNING: JWT_SECRET not set — using an ephemeral dev secret "
          "(tokens will not survive a restart). Set JWT_SECRET in .env for stable sessions.")


# ── password hashing ──────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; truncate so longer passwords don't error.
    return bcrypt.hashpw(password[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain[:72].encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── token mint / verify ───────────────────────────────────────────────────────
def create_access_token(email: str, role: str = "user") -> str:
    payload = {
        "sub": email, "role": role, "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(email: str, role: str = "user") -> str:
    payload = {
        "sub": email, "role": role, "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict:
    """Decode + verify a JWT. Raises HTTPException(401) on any failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Wrong token type")
    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token: missing subject")
    return payload


# ── FastAPI dependencies ──────────────────────────────────────────────────────
def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return auth[7:]


def get_current_user(request: Request) -> dict:
    """Require a valid access token. Returns {email, role}."""
    payload = decode_token(_bearer(request), expected_type="access")
    return {"email": payload["sub"], "role": payload.get("role", "user")}


def require_role(*roles: str):
    """RBAC dependency: require the user to hold one of `roles`."""
    def dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {' or '.join(roles)}")
        return user
    return dep
