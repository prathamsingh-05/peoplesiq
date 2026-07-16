"""Authentication & authorisation.

- PBKDF2-HMAC-SHA256 password hashing (310k iterations, per-user salt).
- JWT bearer tokens (HS256, short-lived).
- Role-based access control: admin / recruiter / hiring_manager.
- Login lockout after repeated failures (brute-force protection).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import User, UserRole

PBKDF2_ITERATIONS = 310_000
_bearer = HTTPBearer(auto_error=False)

# In-memory failed-login tracker {username: (fail_count, first_fail_ts)}
_failed_logins: dict[str, tuple[int, float]] = {}


# --- Passwords --------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iterations, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(iterations)
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, AttributeError):
        return False


# --- Lockout -----------------------------------------------------------------
def check_lockout(username: str) -> None:
    entry = _failed_logins.get(username)
    if not entry:
        return
    count, first_ts = entry
    if count >= config.LOGIN_MAX_ATTEMPTS:
        if time.time() - first_ts < config.LOGIN_LOCKOUT_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked after repeated failed logins. Try again later.",
            )
        _failed_logins.pop(username, None)


def record_failed_login(username: str) -> None:
    count, first_ts = _failed_logins.get(username, (0, time.time()))
    _failed_logins[username] = (count + 1, first_ts)


def clear_failed_logins(username: str) -> None:
    _failed_logins.pop(username, None)


# --- Tokens ------------------------------------------------------------------
def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, config.SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(
            credentials.credentials, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or not found")
    return user


def require_roles(*roles: UserRole):
    allowed = {r.value for r in roles}

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of roles: {', '.join(sorted(allowed))}",
            )
        return user

    return _dep


# Common dependencies
require_recruiter = require_roles(UserRole.admin, UserRole.recruiter)
require_admin = require_roles(UserRole.admin)
require_any_user = get_current_user  # all roles incl. hiring_manager (read-mostly)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""
