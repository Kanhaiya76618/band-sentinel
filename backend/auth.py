"""
Aegis — demo-grade auth (Phase 7).

Lightweight, hackathon-grade sign-in built entirely on the Python standard
library — no new dependencies:

    * passwords are hashed with ``hashlib.pbkdf2_hmac`` (SHA-256, per-user random
      salt, many iterations) and stored as ``pbkdf2_sha256$iters$salt$hash``.
      Plaintext is NEVER stored or logged.
    * sessions are opaque random tokens (``secrets.token_urlsafe``) persisted in
      SQLite with an expiry, carried in an httpOnly cookie.

This is intentionally simple: it is NOT production-hardened (no rate limiting,
email verification, password reset, CSRF tokens, or rotation). See the README.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets

# ---- tunables ------------------------------------------------------------- #
COOKIE_NAME = "aegis_session"
SESSION_DAYS = int(os.getenv("AEGIS_SESSION_DAYS", "7"))
SESSION_SECONDS = SESSION_DAYS * 24 * 3600
MIN_PASSWORD_LEN = 8

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 240_000
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---- password hashing ----------------------------------------------------- #
def hash_password(password: str) -> str:
    """Return ``pbkdf2_sha256$iterations$salt_hex$hash_hex`` — never the plaintext."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a candidate password against a stored hash."""
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters_s))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ---- sessions / validation ------------------------------------------------ #
def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip()))


def password_problem(password: str) -> str | None:
    """Return a human message if the password is unacceptable, else None."""
    if not password or len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    return None
