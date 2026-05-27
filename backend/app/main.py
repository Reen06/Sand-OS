"""FastAPI application factory for the Roku-E8C3 dashboard backend.

Run in production via the venv's uvicorn (see systemd/sand-dashboard.service)
or directly with ``python -m app.main`` for development.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from .api import auth, devices, guest, logs, network, overview, pihole, routing, system, vpn, wifi
from .core.settings import settings
from .db.migrations import init_db
from .db.repo import Database

log = logging.getLogger("sand")

_API_ROUTERS = (auth.router, overview.router, network.router,
                system.router, logs.router, wifi.router, pihole.router,
                vpn.router, routing.router, guest.router, devices.router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = Database(settings.db_path)
    init_db(db, settings.schema_path)
    db.purge_expired_sessions()
    db.prune_events()
    app.state.db = db
    app.state.app_secret = db.get_setting("_app_secret") or "dev-insecure-secret"
    db.log_event("system", "Dashboard backend started")
    log.info("Roku-E8C3 dashboard ready (db=%s)", settings.db_path)
    try:
        yield
    finally:
        db.log_event("system", "Dashboard backend stopping")
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Roku-E8C3 Dashboard", version="0.1.0",
                  docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)

    for router in _API_ROUTERS:
        app.include_router(router, prefix="/api")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Never cache static assets — this is a local dashboard that updates
        # frequently; stale JS/CSS causes hard-to-debug breakage.
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    frontend = settings.frontend_dir

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        """Serve the static dashboard; unknown routes fall back to index.html."""
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        root = frontend.resolve()
        if full_path:
            candidate = (frontend / full_path).resolve()
            if (candidate == root or root in candidate.parents) and candidate.is_file():
                return FileResponse(candidate)
        index = frontend / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse({"detail": "Dashboard frontend not installed"},
                            status_code=404)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=settings.bind_host, port=settings.bind_port,
                log_level="info")
