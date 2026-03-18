from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.schemas.auth import (
    AdminRead,
    InitialSetupRequest,
    LoginRequest,
    SetupStatusResponse,
    TokenResponse,
)
from app.services.auth import AuthService
from app.services.exceptions import ServiceError

router = APIRouter()


@router.get("/setup-status", response_model=SetupStatusResponse)
def setup_status(db: Session = Depends(get_db)) -> SetupStatusResponse:
    return SetupStatusResponse(is_initialized=AuthService(db).is_initialized())


@router.post("/setup", response_model=TokenResponse)
def setup(payload: InitialSetupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        return AuthService(db).create_initial_admin(payload.username, payload.password)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        return AuthService(db).login(payload.username, payload.password)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/me", response_model=AdminRead)
def me(admin=Depends(get_current_admin)) -> AdminRead:
    return AdminRead.model_validate(admin)
