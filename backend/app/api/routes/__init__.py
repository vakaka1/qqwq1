from fastapi import APIRouter

from app.api.routes import accesses, admins, auth, bot, bot_runtime, bots, dashboard, logs, servers, users

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admins.router, prefix="/admins", tags=["admins"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(bots.router, prefix="/bots", tags=["bots"])
api_router.include_router(servers.router, prefix="/servers", tags=["servers"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(accesses.router, prefix="/accesses", tags=["accesses"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
api_router.include_router(bot.router, prefix="/bot", tags=["bot"])
api_router.include_router(bot_runtime.router, prefix="/bot-runtime", tags=["bot-runtime"])
