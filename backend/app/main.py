from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.routes import api_router
from app.config.settings import get_settings
from app.core.logging import configure_logging
from app.db.init_admin import ensure_initial_admin
from app.db.session import SessionLocal
from app.schemas.common import HealthResponse
from app.tasks.scheduler import start_scheduler, stop_scheduler

settings = get_settings()
configure_logging(settings.debug)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.bootstrap_admin_on_startup:
        db = SessionLocal()
        try:
            ensure_initial_admin(db)
        finally:
            db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc))


def _resolve_static_file(requested_path: str) -> Path | None:
    static_dir = settings.static_dir
    if not static_dir.exists():
        return None
    target = (static_dir / requested_path).resolve()
    try:
        target.relative_to(static_dir.resolve())
    except ValueError:
        return None
    if target.is_file():
        return target
    index = static_dir / "index.html"
    return index if index.exists() else None


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith(("api/", "docs", "redoc", "openapi.json", "health")):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    file_path = _resolve_static_file(full_path)
    if file_path:
        return FileResponse(file_path)
    return JSONResponse(
        status_code=503,
        content={"detail": "Admin UI еще не собран. Выполните npm install && npm run build в ./frontend."},
    )
