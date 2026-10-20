"""Sessions, password hashing, role dependencies.

- HMAC-signed session cookie, HttpOnly, SameSite=Lax, 8h expiry.
- PBKDF2-SHA256, 200k iterations.
- Login rate limit per (IP, username) and a looser one per IP, so nobody can lock a victim out by username alone.
  The limiter store is bounded and check-and-record is atomic. It is in-memory, which is fine for a
  single-process PoC; with several workers, move it to Redis (INCR + EXPIRE).
- Unknown usernames still run a full password verify, so login timing doesn't reveal which usernames exist.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import OrderedDict, deque

from fastapi import Depends, HTTPException, Request, Response

from . import db

SECRET = (os.environ.get("SESSION_SECRET") or secrets.token_hex(32)).encode()
SESSION_TTL = 8 * 3600
COOKIE = "kbc_session"
PBKDF2_ITERATIONS = 200_000
LOGIN_WINDOW_S = 15 * 60
LOGIN_MAX_ATTEMPTS = 10  # failures per (IP, username)
LOGIN_MAX_ATTEMPTS_PER_IP = 50  # failures per IP, across usernames
LIMITER_MAX_KEYS = 10_000

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

class SlidingWindowLimiter:
    """At most `limit` hits per key in a sliding `window_s`. Bounded: expired keys are evicted on every
    write and, past `max_keys`, the least recently used key is dropped. Thread-safe and atomic."""

    def __init__(self, limit: int, window_s: float, max_keys: int = LIMITER_MAX_KEYS):
        self.limit = limit
        self.window_s = window_s
        self.max_keys = max_keys
        self._hits: OrderedDict[object, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_s
        # entries are kept in LRU order, so stale keys collect at the front
        while self._hits:
            key, q = next(iter(self._hits.items()))
            if q and q[-1] >= cutoff and len(self._hits) <= self.max_keys:
                break
            self._hits.popitem(last=False)

    def hit(self, key: object) -> float | None:
        """Record a hit and return its token, or None (nothing recorded) if the key is over the limit."""
        now = time.time()
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                q = self._hits[key] = deque()
            self._hits.move_to_end(key)
            while q and q[0] < now - self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return None
            q.append(now)
            self._evict(now)
            return now

    def undo(self, key: object, token: float) -> None:
        with self._lock:
            q = self._hits.get(key)
            if q is not None:
                try:
                    q.remove(token)
                except ValueError:
                    pass

    def __len__(self) -> int:
        return len(self._hits)


_login_by_ip_user = SlidingWindowLimiter(LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_S)
_login_by_ip = SlidingWindowLimiter(LOGIN_MAX_ATTEMPTS_PER_IP, LOGIN_WINDOW_S)
# a valid hash of a random password: verifying against it costs the same as a real user's hash
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def authenticate(conn, username: str, password: str, ip: str):
    """Return the user row, or raise 401 (same body for unknown user and wrong password) or 429.

    Each attempt reserves a slot in both limiters before the password check, so concurrent requests can't
    overshoot. A successful login gives its slots back, so only failures count."""
    username = username.strip().lower()[:64]
    keys = ((_login_by_ip, ip), (_login_by_ip_user, (ip, username)))
    taken = []
    for limiter, key in keys:
        token = limiter.hit(key)
        if token is None:
            for lim, k, t in taken:
                lim.undo(k, t)
            raise HTTPException(status_code=429, detail="Too many login attempts, try again later")
        taken.append((limiter, key, token))
    row = db.get_user(conn, username)
    ok = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not ok:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    for limiter, key, token in taken:
        limiter.undo(key, token)
    return row


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
