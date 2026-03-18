from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import verify_bot_token
from app.db.session import get_db
from app.schemas.bot import BotPingResponse, BotStartRequest, BotTrialResponse, BotUserRead
from app.schemas.common import MessageResponse
from app.schemas.vpn_access import AccessConfigRead
from app.services.bot import BotService
from app.services.exceptions import ServiceError
from app.services.vpn_accesses import VpnAccessService

router = APIRouter(dependencies=[Depends(verify_bot_token)])


@router.post("/start", response_model=MessageResponse)
def start(payload: BotStartRequest, db: Session = Depends(get_db)) -> MessageResponse:
    try:
        return BotService(db).handle_start(payload)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/request-trial", response_model=BotTrialResponse)
def request_trial(payload: BotStartRequest, db: Session = Depends(get_db)) -> BotTrialResponse:
    try:
        return VpnAccessService(db).request_trial(
            bot_code=payload.bot_code,
            telegram_user_id=payload.telegram_user_id,
            username=payload.username,
            first_name=payload.first_name,
            last_name=payload.last_name,
            language_code=payload.language_code,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/user/{telegram_user_id}", response_model=BotUserRead)
def get_user(
    telegram_user_id: int,
    bot_code: str = Query(...),
    db: Session = Depends(get_db),
) -> BotUserRead:
    try:
        return VpnAccessService(db).get_user_status(telegram_user_id, bot_code=bot_code)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/config/{telegram_user_id}", response_model=AccessConfigRead)
def get_user_config(
    telegram_user_id: int,
    bot_code: str = Query(...),
    db: Session = Depends(get_db),
) -> AccessConfigRead:
    try:
        return VpnAccessService(db).get_latest_config_for_user(telegram_user_id, bot_code=bot_code)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/ping", response_model=BotPingResponse)
def ping() -> BotPingResponse:
    return BotPingResponse(status="ok", service="backend")
