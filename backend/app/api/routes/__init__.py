from fastapi import APIRouter

from app.api.routes import (
    accesses,
    admins,
    auth,
    bot,
    bot_runtime,
    bots,
    dashboard,
    freekassa,
    logs,
    monetization,
    payment_domains,
    servers,
    site_runtime,
    sites,
    system_settings,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admins.router, prefix="/admins", tags=["admins"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(freekassa.router, prefix="/freekassa", tags=["freekassa"])
api_router.include_router(bots.router, prefix="/bots", tags=["bots"])
api_router.include_router(servers.router, prefix="/servers", tags=["servers"])
api_router.include_router(sites.router, prefix="/sites", tags=["sites"])
api_router.include_router(payment_domains.router, prefix="/payment-domains", tags=["payment-domains"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(accesses.router, prefix="/accesses", tags=["accesses"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
api_router.include_router(system_settings.router, prefix="/system-settings", tags=["system-settings"])
api_router.include_router(monetization.router, prefix="/monetization", tags=["monetization"])
api_router.include_router(bot.router, prefix="/bot", tags=["bot"])
api_router.include_router(bot_runtime.router, prefix="/bot-runtime", tags=["bot-runtime"])
api_router.include_router(site_runtime.router, prefix="/site-runtime", tags=["site-runtime"])
