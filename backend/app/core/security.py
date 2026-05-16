"""Password hashing and token helpers — standard library only.

Passwords are hashed with scrypt (memory-hard). Sessions use random opaque
tokens stored server-side in the database. CSRF tokens are derived from the
session token with an HMAC keyed by a per-install secret, so no extra storage
is needed and a CSRF token is invalidated automatically when its session ends.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_PREFIX = "scrypt"


def hash_password(plain: str) -> str:
    """Return an encoded scrypt hash: scrypt$N$r$p$salt_hex$hash_hex."""
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(plain.encode(), salt=salt, n=_SCRYPT_N,
                        r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"{_PREFIX}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    """Constant-time verification of a plaintext password against a hash."""
    try:
        prefix, n, r, p, salt_hex, hash_hex = stored.split("$")
        if prefix != _PREFIX:
            return False
        dk = hashlib.scrypt(plain.encode(), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def new_token(nbytes: int = 32) -> str:
    """Cryptographically strong, URL-safe opaque token."""
    return secrets.token_urlsafe(nbytes)


def derive_csrf(secret: str, session_token: str) -> str:
    """Derive a CSRF token bound to a session."""
    return hmac.new(secret.encode(), session_token.encode(), hashlib.sha256).hexdigest()


def csrf_ok(secret: str, session_token: str, presented: str) -> bool:
    return hmac.compare_digest(derive_csrf(secret, session_token), presented or "")


def password_strength_error(pw: str) -> str | None:
    """Return a human-readable reason a password is too weak, or None if OK."""
    if len(pw) < 10:
        return "Password must be at least 10 characters."
    classes = sum([
        any(c.islower() for c in pw),
        any(c.isupper() for c in pw),
        any(c.isdigit() for c in pw),
        any(not c.isalnum() for c in pw),
    ])
    if classes < 3:
        return "Use at least three of: lowercase, uppercase, digits, symbols."
    return None
