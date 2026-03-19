from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.config.settings import get_settings
from app.db.session import get_db
from app.schemas.site import (
    SiteConnectionPayload,
    SiteConnectionProbeResponse,
    SiteDeleteRead,
    SiteDeploymentPlanRead,
    SitePreviewRead,
    SiteProvisionRequest,
    SiteRead,
    SiteTemplateRead,
)
from app.services.exceptions import ServiceError
from app.services.sites import SiteService

router = APIRouter(dependencies=[Depends(get_current_admin)])
settings = get_settings()


@router.get("/", response_model=list[SiteRead])
def list_sites(db: Session = Depends(get_db)) -> list[SiteRead]:
    return SiteService(db).list_sites()


@router.get("/templates", response_model=list[SiteTemplateRead])
def list_templates(db: Session = Depends(get_db)) -> list[SiteTemplateRead]:
    return SiteService(db).list_templates()


@router.post("/probe-connection", response_model=SiteConnectionProbeResponse)
def probe_connection(
    payload: SiteConnectionPayload,
    db: Session = Depends(get_db),
) -> SiteConnectionProbeResponse:
    try:
        return SiteService(db).probe_connection(payload)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/preview", response_model=SitePreviewRead)
def preview_site(
    payload: SiteProvisionRequest,
    db: Session = Depends(get_db),
) -> SitePreviewRead:
    try:
        return SiteService(db).render_preview(payload)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/plan", response_model=SiteDeploymentPlanRead)
def build_plan(
    payload: SiteProvisionRequest,
    db: Session = Depends(get_db),
) -> SiteDeploymentPlanRead:
    try:
        return SiteService(db).build_plan(payload)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/", response_model=SiteRead)
def create_site(
    payload: SiteProvisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> SiteRead:
    try:
        public_api_base_url = f"{str(request.base_url).rstrip('/')}{settings.api_v1_prefix}"
        return SiteService(db).create_site(
            payload,
            actor_id=str(admin.id),
            public_api_base_url=public_api_base_url,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{site_id}/deploy", response_model=SiteRead)
def redeploy_site(
    site_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> SiteRead:
    try:
        public_api_base_url = f"{str(request.base_url).rstrip('/')}{settings.api_v1_prefix}"
        return SiteService(db).deploy_site(
            site_id,
            actor_id=str(admin.id),
            public_api_base_url=public_api_base_url,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{site_id}/refresh-cloudflare-url", response_model=SiteRead)
def refresh_cloudflare_url(
    site_id: str,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> SiteRead:
    try:
        return SiteService(db).refresh_cloudflare_public_url(site_id, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/{site_id}", response_model=SiteDeleteRead)
def delete_site(
    site_id: str,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> SiteDeleteRead:
    try:
        return SiteService(db).delete_site(site_id, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
