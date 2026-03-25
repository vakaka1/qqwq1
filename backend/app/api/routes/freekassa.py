from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.audit import AuditService
from app.services.freekassa import FreeKassaService
from app.services.exceptions import ServiceError
from app.services.monetization import MonetizationService

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
    monetization = MonetizationService(db)
    payload = await _extract_request_payload(request)
    source_ip = service.resolve_source_ip(request.headers, request.client.host if request.client else None)
    try:
        notification = service.verify_notification(payload, source_ip=source_ip)
        monetization.apply_successful_payment_notification(notification)
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
    return PlainTextResponse("YES")


@router.get("/pay/{payment_token}")
def freekassa_redirect(payment_token: str, request: Request, db: Session = Depends(get_db)):
    service = FreeKassaService()
    monetization = MonetizationService(db)
    source_ip = service.resolve_source_ip(request.headers, request.client.host if request.client else None)
    try:
        redirect_url = monetization.prepare_payment_redirect(payment_token, source_ip=source_ip)
    except ServiceError as exc:
        return HTMLResponse(
            service.render_error_page(
                title="Не удалось открыть оплату",
                message=exc.message,
                order_id=payment_token,
            ),
            status_code=exc.status_code,
        )
    return RedirectResponse(url=redirect_url, status_code=307)


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
