"""Sessions, password hashing, role dependencies.

- HMAC-signed session cookie, HttpOnly, SameSite=Lax, 8h expiry.
- PBKDF2-SHA256, 200k iterations.
- Login rate limit per username and per IP (in-memory; fine for a single-process PoC).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, Response

from . import db

SECRET = (os.environ.get("SESSION_SECRET") or secrets.token_hex(32)).encode()
SESSION_TTL = 8 * 3600
COOKIE = "kbc_session"
PBKDF2_ITERATIONS = 200_000
LOGIN_WINDOW_S = 15 * 60
LOGIN_MAX_ATTEMPTS = 10

# ----------------------------------------------------------------------------------
# Passwords
# ----------------------------------------------------------------------------------


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# ----------------------------------------------------------------------------------
# Session cookie
# ----------------------------------------------------------------------------------


def _sign(payload: bytes) -> str:
    return hmac.new(SECRET, payload, hashlib.sha256).hexdigest()


def make_session(user_id: int, role: str) -> str:
    payload = json.dumps({"uid": user_id, "role": role, "exp": int(time.time()) + SESSION_TTL}).encode()
    b = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{b}.{_sign(payload)}"


def read_session(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    b, sig = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4))
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(_sign(payload), sig):
        return None
    try:
        data = json.loads(payload)
    except ValueError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data


def set_session_cookie(response: Response, token: str, secure: bool = False) -> None:
    response.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="lax", secure=secure, path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


# ----------------------------------------------------------------------------------
# Rate limiting
# ----------------------------------------------------------------------------------

_attempts: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str) -> None:
    now = time.time()
    q = _attempts[key]
    while q and q[0] < now - LOGIN_WINDOW_S:
        q.popleft()
    if len(q) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many login attempts, try again later")


def record_attempt(key: str) -> None:
    _attempts[key].append(time.time())


# ----------------------------------------------------------------------------------
# Dependencies
# ----------------------------------------------------------------------------------


class Principal:
    def __init__(self, user_id: int, role: str, customer_id: int | None, username: str):
        self.user_id = user_id
        self.role = role
        self.customer_id = customer_id
        self.username = username


def current_user(request: Request) -> Principal:
    sess = read_session(request.cookies.get(COOKIE))
    if not sess:
        raise HTTPException(status_code=401, detail="Not logged in")
    with db.tx() as conn:
        row = db.get_user_by_id(conn, int(sess["uid"]))
    if not row:
        raise HTTPException(status_code=401, detail="Unknown user")
    return Principal(row["id"], row["role"], row["customer_id"], row["username"])


def require_customer(user: Principal = Depends(current_user)) -> Principal:
    if user.role != "customer" or user.customer_id is None:
        raise HTTPException(status_code=403, detail="Customer login required")
    return user


def require_advisor(user: Principal = Depends(current_user)) -> Principal:
    if user.role != "advisor":
        raise HTTPException(status_code=403, detail="Advisor role required")
    return user
