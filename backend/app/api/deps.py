"""Shared FastAPI dependencies — database access, authentication, CSRF."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status

from ..core.security import csrf_ok
from ..db.repo import Database


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_secret(request: Request) -> str:
    return request.app.state.app_secret


def current_session(request: Request,
                    db: Database = Depends(get_db)) -> Optional[dict]:
    token = request.cookies.get("roku_session", "")
    return db.get_session(token)


def require_auth(session: Optional[dict] = Depends(current_session)) -> dict:
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Authentication required")
    return session


def require_csrf(session: dict = Depends(require_auth),
                 secret: str = Depends(get_secret),
                 x_roku_csrf: str = Header(default="")) -> dict:
    """Protect state-changing requests with a session-bound CSRF token."""
    if not csrf_ok(secret, session["token"], x_roku_csrf):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Invalid or missing CSRF token")
    return session
