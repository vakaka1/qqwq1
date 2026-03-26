from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_admin
from app.config.settings import get_settings
from app.db.session import get_db
from app.schemas.payment_domain import (
    PaymentDomainDeleteRead,
    PaymentDomainDeploymentPlanRead,
    PaymentDomainProvisionRequest,
    PaymentDomainRead,
)
from app.schemas.site import SiteConnectionPayload, SiteConnectionProbeResponse
from app.services.exceptions import ServiceError
from app.services.payment_domains import PaymentDomainService

router = APIRouter(dependencies=[Depends(get_current_admin)])
settings = get_settings()


@router.get("/", response_model=list[PaymentDomainRead])
def list_payment_domains(db: Session = Depends(get_db)) -> list[PaymentDomainRead]:
    return PaymentDomainService(db).list_payment_domains()


@router.post("/probe-connection", response_model=SiteConnectionProbeResponse)
def probe_connection(
    payload: SiteConnectionPayload,
    db: Session = Depends(get_db),
) -> SiteConnectionProbeResponse:
    try:
        return PaymentDomainService(db).probe_connection(payload)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/plan", response_model=PaymentDomainDeploymentPlanRead)
def build_plan(
    payload: PaymentDomainProvisionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PaymentDomainDeploymentPlanRead:
    try:
        public_api_base_url = f"{str(request.base_url).rstrip('/')}{settings.api_v1_prefix}"
        return PaymentDomainService(db).build_plan(payload, public_api_base_url=public_api_base_url)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/", response_model=PaymentDomainRead)
def create_payment_domain(
    payload: PaymentDomainProvisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> PaymentDomainRead:
    try:
        public_api_base_url = f"{str(request.base_url).rstrip('/')}{settings.api_v1_prefix}"
        return PaymentDomainService(db).create_payment_domain(
            payload,
            actor_id=str(admin.id),
            public_api_base_url=public_api_base_url,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{payment_domain_id}/deploy", response_model=PaymentDomainRead)
def redeploy_payment_domain(
    payment_domain_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> PaymentDomainRead:
    try:
        public_api_base_url = f"{str(request.base_url).rstrip('/')}{settings.api_v1_prefix}"
        return PaymentDomainService(db).deploy_payment_domain(
            payment_domain_id,
            actor_id=str(admin.id),
            public_api_base_url=public_api_base_url,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/{payment_domain_id}", response_model=PaymentDomainDeleteRead)
def delete_payment_domain(
    payment_domain_id: str,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> PaymentDomainDeleteRead:
    try:
        return PaymentDomainService(db).delete_payment_domain(payment_domain_id, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
