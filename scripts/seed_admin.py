from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.base import Base  # noqa: E402
from app.db.init_admin import ensure_initial_admin  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402

Base.metadata.create_all(bind=engine)

db = SessionLocal()
try:
    ensure_initial_admin(db)
finally:
    db.close()

print("Администратор создан или уже существует.")

