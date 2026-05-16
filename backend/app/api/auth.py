"""Authentication: first-run setup, login, logout, session status."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..core.security import (derive_csrf, hash_password, new_token,
                             password_strength_error, verify_password)
from ..core.settings import settings
from ..db.repo import Database
from .deps import current_session, get_db, get_secret, require_csrf

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE = "roku_session"
_MAX_FAILS = 8          # failed logins per window before lockout
_WINDOW_MIN = 5


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class SetupBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ChangePwBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def _expiry() -> str:
    return (datetime.now(timezone.utc)
            + timedelta(hours=settings.session_ttl_hours)
            ).strftime("%Y-%m-%d %H:%M:%S")


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict",
                        max_age=settings.session_ttl_hours * 3600, path="/")


def _recent_failures(db: Database) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM events WHERE category='auth' "
        "AND level='warn' AND created_at > datetime('now', ?)",
        (f"-{_WINDOW_MIN} minutes",))
    return int(row["n"]) if row else 0


@router.get("/status")
def auth_status(db: Database = Depends(get_db),
                secret: str = Depends(get_secret),
                session=Depends(current_session)) -> dict:
    needs_setup = db.get_setting("dashboard_password") is None
    out = {"authenticated": bool(session), "needs_setup": needs_setup,
           "hostname": db.get_setting("hostname", settings.hostname)}
    if session:
        out["csrf"] = derive_csrf(secret, session["token"])
    return out


@router.post("/setup")
def setup(body: SetupBody, db: Database = Depends(get_db)) -> dict:
    """Set the initial dashboard password. Allowed only before one exists."""
    if db.get_setting("dashboard_password") is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Dashboard password is already configured")
    err = password_strength_error(body.password)
    if err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, err)
    db.set_setting("dashboard_password", hash_password(body.password))
    db.log_event("auth", "Initial dashboard password set")
    return {"ok": True}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response,
          db: Database = Depends(get_db),
          secret: str = Depends(get_secret)) -> dict:
    if _recent_failures(db) >= _MAX_FAILS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many failed attempts. Wait a few minutes.")
    stored = db.get_setting("dashboard_password")
    client_ip = request.client.host if request.client else ""
    if not stored or not verify_password(body.password, stored):
        db.log_event("auth", "Failed dashboard login", level="warn",
                     detail=client_ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password")
    token = new_token()
    db.create_session(token, _expiry(),
                      request.headers.get("user-agent", "")[:200], client_ip)
    db.purge_expired_sessions()
    _set_cookie(response, token)
    db.log_event("auth", "Dashboard login", detail=client_ip)
    return {"ok": True, "csrf": derive_csrf(secret, token)}


@router.post("/logout")
def logout(request: Request, response: Response,
           db: Database = Depends(get_db)) -> dict:
    token = request.cookies.get(COOKIE, "")
    if token:
        db.delete_session(token)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/change-password")
def change_password(body: ChangePwBody, db: Database = Depends(get_db),
                    session: dict = Depends(require_csrf)) -> dict:
    stored = db.get_setting("dashboard_password") or ""
    if not verify_password(body.current_password, stored):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Current password is incorrect")
    err = password_strength_error(body.new_password)
    if err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, err)
    db.set_setting("dashboard_password", hash_password(body.new_password))
    # Invalidate all other sessions; keep the current one.
    db.execute("DELETE FROM sessions WHERE token != ?", (session["token"],))
    db.log_event("auth", "Dashboard password changed")
    return {"ok": True}
