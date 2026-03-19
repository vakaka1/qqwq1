from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import get_settings
from app.schemas.site import SiteTemplateRead
from app.services.exceptions import ServiceError
from app.utils.naming import slugify_identifier

_PLACEHOLDER_PATTERN = re.compile(r"{{\s*([A-Z0-9_]+)\s*}}")


@dataclass(frozen=True, slots=True)
class SiteTemplateDefinition:
    key: str
    name: str
    filename: str
    description: str
    source_path: Path
    placeholders: list[str]
    is_default: bool = False


class SiteTemplateService:
    def __init__(self) -> None:
        settings = get_settings()
        self.project_dir = settings.project_dir
        self.template_dir = self.project_dir / "site_templates"

    def _humanize_name(self, path: Path) -> str:
        stem = path.stem.replace("-", " ").replace("_", " ").strip()
        return stem.title() or "Template"

    def _build_definition(self, path: Path, *, is_default: bool) -> SiteTemplateDefinition:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ServiceError(f"Не удалось прочитать шаблон {path.name}", 500) from exc

        key = slugify_identifier(path.stem, default="site-template", limit=60)
        placeholders = sorted({match.group(1) for match in _PLACEHOLDER_PATTERN.finditer(raw)})
        description = (
            "Базовый HTML-шаблон для сайта."
            if is_default
            else "Пользовательский HTML-шаблон из папки site_templates."
        )
        return SiteTemplateDefinition(
            key=key,
            name=self._humanize_name(path),
            filename=path.name,
            description=description,
            source_path=path,
            placeholders=placeholders,
            is_default=is_default,
        )

    def list_definitions(self) -> list[SiteTemplateDefinition]:
        templates: list[SiteTemplateDefinition] = []
        used_keys: set[str] = set()

        if self.template_dir.is_dir():
            for path in sorted(self.template_dir.glob("*.html")):
                definition = self._build_definition(path, is_default=path.name == "site.html")
                if definition.key in used_keys:
                    continue
                templates.append(definition)
                used_keys.add(definition.key)

        if not templates:
            raise ServiceError(
                f"В папке {self.template_dir} не найдено ни одного HTML-шаблона",
                500,
            )
        return templates

    def list_templates(self) -> list[SiteTemplateRead]:
        return [
            SiteTemplateRead(
                key=item.key,
                name=item.name,
                filename=item.filename,
                description=item.description,
                source_path=str(item.source_path),
                placeholders=item.placeholders,
                is_default=item.is_default,
            )
            for item in self.list_definitions()
        ]

    def get_definition_or_404(self, key: str) -> SiteTemplateDefinition:
        for item in self.list_definitions():
            if item.key == key:
                return item
        raise ServiceError("Шаблон не найден", 404)

    def render(self, key: str, context: dict[str, str]) -> str:
        definition = self.get_definition_or_404(key)
        raw = definition.source_path.read_text(encoding="utf-8")
        escaped_context = {
            name: html.escape(value, quote=True)
            for name, value in context.items()
        }

        def replace(match: re.Match[str]) -> str:
            placeholder = match.group(1)
            if placeholder in escaped_context:
                return escaped_context[placeholder]
            return match.group(0)

        return _PLACEHOLDER_PATTERN.sub(replace, raw)
