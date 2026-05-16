"""Logs router — recent journal output for known sources."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..db.repo import Database
from ..services import logs as logsvc
from .deps import get_db, require_auth

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/sources")
def sources(_=Depends(require_auth)) -> dict:
    return {"sources": logsvc.sources()}


@router.get("")
def get_logs(source: str = Query(default="system"),
             lines: int = Query(default=200, ge=1, le=1000),
             _=Depends(require_auth)) -> dict:
    return logsvc.journal(source, lines)


@router.get("/events")
def events(limit: int = Query(default=100, ge=1, le=1000),
           category: str | None = Query(default=None),
           db: Database = Depends(get_db), _=Depends(require_auth)) -> dict:
    return {"events": db.recent_events(limit, category)}
