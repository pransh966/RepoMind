"""
Password hashing + JWT tokens.

Deliberately dependency-light: password hashing uses stdlib hashlib.pbkdf2_hmac
(no bcrypt/passlib, which need C extensions that have been a pain to install
on this project already). JWT uses PyJWT, which is pure Python.

This is enough security for a local/dev/demo tool. Before running this
anywhere multi-tenant on the public internet, put it behind HTTPS and set a
real random JWT_SECRET in .env.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

import jwt

from app.config import settings

PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> tuple[str, str]:
    """Returns (password_hash_hex, salt_hex)."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return hmac.compare_digest(check.hex(), password_hash)


def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": int(time.time()) + settings.jwt_expire_minutes * 60,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired tokens -- let the caller catch it."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
