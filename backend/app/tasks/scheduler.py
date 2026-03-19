from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.db.session import SessionLocal
from app.services.system_settings import load_effective_system_settings
from app.services.vpn_accesses import VpnAccessService

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def expire_accesses_job() -> None:
    db = SessionLocal()
    try:
        service = VpnAccessService(db)
        processed = service.expire_due_accesses()
        if processed:
            logger.info("Планировщик пометил истекшими %s доступ(ов)", processed)
        
        notified = service.notify_approaching_expiration()
        if notified:
            logger.info("Планировщик отправил %s уведомление(й) о скором истечении", notified)
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    interval_minutes = load_effective_system_settings().scheduler_interval_minutes
    scheduler.add_job(
        expire_accesses_job,
        "interval",
        minutes=interval_minutes,
        id="expire_accesses",
        replace_existing=True,
    )
    scheduler.start()


def reload_scheduler(interval_minutes: int | None = None) -> None:
    resolved_minutes = interval_minutes or load_effective_system_settings().scheduler_interval_minutes
    if scheduler.get_job("expire_accesses"):
        scheduler.reschedule_job("expire_accesses", trigger="interval", minutes=resolved_minutes)
        return
    if scheduler.running:
        scheduler.add_job(
            expire_accesses_job,
            "interval",
            minutes=resolved_minutes,
            id="expire_accesses",
            replace_existing=True,
        )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
