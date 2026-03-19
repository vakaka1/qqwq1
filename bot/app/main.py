from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import get_settings
from app.services.backend_client import BackendClient
from app.services.managed_bot_runner import ManagedBotRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Managed Bot Runner API")
runner: ManagedBotRunner | None = None


class SendMessageRequest(BaseModel):
    bot_code: str
    chat_id: int
    text: str
    image_url: str | None = None
    image_base64: str | None = None
    image_filename: str | None = None
    parse_mode: str | None = "Markdown"


class SendBulkMessageRequest(BaseModel):
    bot_code: str
    chat_ids: list[int]
    text: str
    image_url: str | None = None
    image_base64: str | None = None
    image_filename: str | None = None
    parse_mode: str | None = "Markdown"


def _verify_runner_token(request: Request) -> None:
    settings = get_settings()
    auth_header = request.headers.get("X-Runner-Token")
    if auth_header != settings.bot_runner_token:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/webhooks/{bot_code}")
async def telegram_webhook(bot_code: str, request: Request) -> Any:
    if not runner:
        return Response(status_code=503)
    
    update_data = await request.json()
    asyncio.create_task(runner.feed_update(bot_code, update_data))
    return {"ok": True}


@app.post("/internal/send-message")
async def send_message(payload: SendMessageRequest, request: Request) -> Any:
    _verify_runner_token(request)

    if not runner:
        raise HTTPException(status_code=503, detail="Runner not initialized")

    success = await runner.send_message(
        payload.bot_code,
        payload.chat_id,
        payload.text,
        image_url=payload.image_url,
        image_base64=payload.image_base64,
        image_filename=payload.image_filename,
        parse_mode=payload.parse_mode,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send message")
    
    return {"ok": True}


@app.post("/internal/send-bulk-message")
async def send_bulk_message(payload: SendBulkMessageRequest, request: Request) -> Any:
    _verify_runner_token(request)

    if not runner:
        raise HTTPException(status_code=503, detail="Runner not initialized")

    success_count = await runner.send_bulk_message(
        payload.bot_code,
        payload.chat_ids,
        payload.text,
        image_url=payload.image_url,
        image_base64=payload.image_base64,
        image_filename=payload.image_filename,
        parse_mode=payload.parse_mode,
    )
    return {"ok": True, "success_count": success_count}


@app.get("/health")
async def health_check() -> Any:
    return {"status": "ok", "active_bots": list(runner.sessions.keys()) if runner else []}


async def run_runner() -> None:
    global runner
    settings = get_settings()
    backend_client = BackendClient()
    runner = ManagedBotRunner(backend_client, settings.sync_interval_seconds)

    try:
        await backend_client.ping()
    except Exception as exc:
        logger.warning("Не удалось проверить backend при старте bot-runner: %s", exc)

    try:
        await runner.run_forever()
    finally:
        await runner.shutdown()
        await backend_client.close()


@app.on_event("startup")
async def startup_event() -> None:
    asyncio.create_task(run_runner())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
