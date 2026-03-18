from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings

settings = get_settings()
is_sqlite = settings.database_url.startswith("sqlite")
if is_sqlite:
    raw_path = settings.database_url.replace("sqlite:///", "", 1)
    if raw_path and raw_path != ":memory:":
        db_path = Path(raw_path if not raw_path.startswith("/") else f"/{raw_path.lstrip('/')}")
        db_path.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    settings.database_url,
    future=True,
    echo=settings.debug,
    connect_args={"check_same_thread": False} if is_sqlite else {},
)


if is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
