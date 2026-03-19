from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps.auth import get_current_admin
from app.db.session import get_db
from app.schemas.managed_bot import ManagedBotCreate, ManagedBotMassMailing, ManagedBotRead, ManagedBotUpdate
from app.services.exceptions import ServiceError
from app.services.managed_bots import ManagedBotService
from app.services.vpn_accesses import VpnAccessService

router = APIRouter(dependencies=[Depends(get_current_admin)])
MAX_MAILING_IMAGE_SIZE_BYTES = 10 * 1024 * 1024


def _resolve_upload_filename(image: StarletteUploadFile) -> str:
    filename = Path(image.filename or "").name.strip()
    if filename and filename not in {".", ".."}:
        return filename
    suffix = mimetypes.guess_extension(image.content_type or "") or ".jpg"
    return f"mailing-image{suffix}"


async def _parse_mailing_request(request: Request) -> tuple[str, str | None, bytes | None, str | None]:
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" not in content_type:
        try:
            payload = ManagedBotMassMailing.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Некорректное тело запроса") from exc
        return payload.text.strip(), (payload.image_url or "").strip() or None, None, None

    form = await request.form()
    raw_text = form.get("text")
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    raw_image = form.get("image")
    if raw_image in (None, ""):
        return text, None, None, None
    if not isinstance(raw_image, StarletteUploadFile):
        raise HTTPException(status_code=422, detail="Файл изображения передан некорректно")
    if raw_image.content_type and not raw_image.content_type.lower().startswith("image/"):
        await raw_image.close()
        raise HTTPException(status_code=422, detail="Можно загрузить только изображение")

    image_filename = _resolve_upload_filename(raw_image)
    image_bytes = await raw_image.read()
    await raw_image.close()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Файл изображения пустой")
    if len(image_bytes) > MAX_MAILING_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=422, detail="Изображение должно быть не больше 10 МБ")
    return text, None, image_bytes, image_filename


@router.get("/", response_model=list[ManagedBotRead])
def list_bots(db: Session = Depends(get_db)) -> list[ManagedBotRead]:
    return ManagedBotService(db).list_bots()


@router.post("/", response_model=ManagedBotRead)
def create_bot(
    payload: ManagedBotCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> ManagedBotRead:
    try:
        return ManagedBotService(db).create_bot(payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.put("/{managed_bot_id}", response_model=ManagedBotRead)
def update_bot(
    managed_bot_id: str,
    payload: ManagedBotUpdate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> ManagedBotRead:
    try:
        return ManagedBotService(db).update_bot(managed_bot_id, payload, actor_id=str(admin.id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.delete("/{managed_bot_id}")
def delete_bot(
    managed_bot_id: str,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> dict:
    try:
        ManagedBotService(db).delete_bot(managed_bot_id, actor_id=str(admin.id))
        return {"message": "Бот удален"}
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{managed_bot_id}/mailing")
async def send_mailing(
    managed_bot_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> dict:
    try:
        text, image_url, image_bytes, image_filename = await _parse_mailing_request(request)
        if not text:
            raise HTTPException(status_code=422, detail="Текст рассылки обязателен")
        bot = ManagedBotService(db).get_or_404(managed_bot_id)
        count = VpnAccessService(db).send_mass_mailing(
            bot.code,
            text,
            image_url=image_url,
            image_bytes=image_bytes,
            image_filename=image_filename,
        )
        return {"message": f"Рассылка отправлена {count} пользователям"}
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
