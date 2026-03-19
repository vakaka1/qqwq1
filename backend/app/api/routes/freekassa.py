from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.audit import AuditService
from app.services.freekassa import FreeKassaService
from app.services.exceptions import ServiceError

router = APIRouter()


async def _extract_request_payload(request: Request) -> dict[str, str]:
    payload = {str(key): str(value) for key, value in request.query_params.items()}
    form = await request.form()
    payload.update({str(key): str(value) for key, value in form.items()})
    return payload


@router.post("/notify", response_class=PlainTextResponse)
async def freekassa_notify(request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    service = FreeKassaService()
    audit = AuditService(db)
    payload = await _extract_request_payload(request)
    source_ip = service.resolve_source_ip(request.headers, request.client.host if request.client else None)
    try:
        notification = service.verify_notification(payload, source_ip=source_ip)
    except ServiceError as exc:
        audit.log(
            actor_type="payment_gateway",
            actor_id=source_ip,
            event_type="freekassa_notification_rejected",
            entity_type="freekassa_payment",
            entity_id=payload.get("MERCHANT_ORDER_ID"),
            level="warning",
            message=f"Отклонено уведомление FreeKassa: {exc.message}",
            payload={"source_ip": source_ip, "raw": payload},
        )
        db.commit()
        return PlainTextResponse(exc.message, status_code=exc.status_code)

    audit.log(
        actor_type="payment_gateway",
        actor_id=source_ip,
        event_type="freekassa_notification_accepted",
        entity_type="freekassa_payment",
        entity_id=notification.merchant_order_id,
        message=f"Принято уведомление FreeKassa по заказу {notification.merchant_order_id}",
        payload=notification.model_dump(),
    )
    db.commit()
    return PlainTextResponse("YES")


@router.post("/success", response_class=HTMLResponse)
async def freekassa_success(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    service = FreeKassaService()
    audit = AuditService(db)
    payload = await _extract_request_payload(request)
    source_ip = service.resolve_source_ip(request.headers, request.client.host if request.client else None)
    audit.log(
        actor_type="payment_gateway",
        actor_id=source_ip,
        event_type="freekassa_return_success",
        entity_type="freekassa_payment",
        entity_id=payload.get("MERCHANT_ORDER_ID") or payload.get("paymentId"),
        message="Пользователь вернулся из FreeKassa по success URL",
        payload={"source_ip": source_ip, "raw": payload},
    )
    db.commit()
    return HTMLResponse(service.render_return_page(outcome="success", payload=payload))


@router.post("/fail", response_class=HTMLResponse)
async def freekassa_fail(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    service = FreeKassaService()
    audit = AuditService(db)
    payload = await _extract_request_payload(request)
    source_ip = service.resolve_source_ip(request.headers, request.client.host if request.client else None)
    audit.log(
        actor_type="payment_gateway",
        actor_id=source_ip,
        event_type="freekassa_return_fail",
        entity_type="freekassa_payment",
        entity_id=payload.get("MERCHANT_ORDER_ID") or payload.get("paymentId"),
        level="warning",
        message="Пользователь вернулся из FreeKassa по fail URL",
        payload={"source_ip": source_ip, "raw": payload},
    )
    db.commit()
    return HTMLResponse(service.render_return_page(outcome="failure", payload=payload))
