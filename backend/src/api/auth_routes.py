"""
ESGenuine — /v1/auth routes (register / login / refresh / me).

Users live in public.users, accessed ONLY here via DATABASE_URL (psycopg2) — never the
public anon key — so bcrypt password hashes are never exposed to the browser-side key.
"""

import os
import psycopg2
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, get_current_user,
)

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


def _conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured for auth.")
    return psycopg2.connect(url)


class Credentials(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


def _tokens(email: str, role: str) -> dict:
    return {
        "access_token": create_access_token(email, role),
        "refresh_token": create_refresh_token(email, role),
        "token_type": "bearer",
        "email": email,
        "role": role,
    }


@router.post("/register")
def register(body: Credentials):
    """Open self-registration → creates a role='user' account and returns tokens."""
    email = body.email.strip().lower()
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    pw_hash = hash_password(body.password)
    conn = _conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Email already registered.")
            cur.execute(
                "INSERT INTO users (email, password_hash, role) VALUES (%s, %s, 'user')",
                (email, pw_hash),
            )
    finally:
        conn.close()
    return _tokens(email, "user")


@router.post("/login")
def login(body: Credentials):
    email = body.email.strip().lower()
    conn = _conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT password_hash, role FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
    finally:
        conn.close()
    # Verify even when the user is missing-ish to keep the failure path uniform.
    if not row or not verify_password(body.password, row[0]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return _tokens(email, row[1])


@router.post("/refresh")
def refresh(body: RefreshIn):
    payload = decode_token(body.refresh_token, expected_type="refresh")
    return _tokens(payload["sub"], payload.get("role", "user"))


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user
