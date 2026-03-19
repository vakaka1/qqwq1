from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.auth import verify_site_runtime_token
from app.db.session import get_db
from app.schemas.site import (
    SitePublicUrlReportRequest,
    SiteRuntimeConfigRequest,
    SiteRuntimeConfigResponse,
)
from app.services.exceptions import ServiceError
from app.services.sites import SiteService
from app.services.vpn_accesses import VpnAccessService

router = APIRouter(dependencies=[Depends(verify_site_runtime_token)])


@router.post("/request-config", response_model=SiteRuntimeConfigResponse)
def request_site_config(
    payload: SiteRuntimeConfigRequest,
    db: Session = Depends(get_db),
) -> SiteRuntimeConfigResponse:
    try:
        return VpnAccessService(db).request_site_trial(
            site_code=payload.site_code,
            visitor_token=payload.visitor_token,
            client_ip=payload.client_ip,
            user_agent=payload.user_agent,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/report-public-url", response_model=dict[str, str])
def report_site_public_url(
    payload: SitePublicUrlReportRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        return SiteService(db).report_cloudflare_public_url(
            site_code=payload.site_code,
            public_url=payload.public_url,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
