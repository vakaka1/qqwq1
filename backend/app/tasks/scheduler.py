from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config.settings import get_settings
from app.db.session import SessionLocal
from app.services.vpn_accesses import VpnAccessService

logger = logging.getLogger(__name__)
settings = get_settings()
scheduler = BackgroundScheduler(timezone="UTC")


def expire_accesses_job() -> None:
    db = SessionLocal()
    try:
        processed = VpnAccessService(db).expire_due_accesses()
        if processed:
            logger.info("Планировщик пометил истекшими %s доступ(ов)", processed)
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        expire_accesses_job,
        "interval",
        minutes=settings.scheduler_interval_minutes,
        id="expire_accesses",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

