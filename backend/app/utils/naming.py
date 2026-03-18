from __future__ import annotations

import re
import unicodedata


_COMMON_PRODUCT_ALIASES = {
    "tg": "telegram",
    "telegram-config": "telegram",
    "telegram-access": "telegram",
    "web": "site",
    "website": "site",
}


def slugify_identifier(value: str | None, *, default: str = "item", limit: int = 40) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_value = re.sub(r"[^a-z0-9]+", "-", ascii_value)
    ascii_value = re.sub(r"-{2,}", "-", ascii_value).strip("-")
    if not ascii_value:
        ascii_value = default
    return ascii_value[:limit].rstrip("-") or default


def build_unique_slug(base: str, existing: set[str], *, limit: int = 40) -> str:
    candidate = base[:limit].rstrip("-")
    if candidate not in existing:
        return candidate

    suffix = 2
    while True:
        suffix_value = f"-{suffix}"
        trimmed = candidate[: max(1, limit - len(suffix_value))].rstrip("-")
        next_candidate = f"{trimmed}{suffix_value}"
        if next_candidate not in existing:
            return next_candidate
        suffix += 1


def infer_channel_name(product_code: str | None) -> str:
    normalized = slugify_identifier(product_code, default="telegram", limit=24)
    alias = _COMMON_PRODUCT_ALIASES.get(normalized)
    if alias:
        return alias
    if "telegram" in normalized:
        return "telegram"
    if "site" in normalized:
        return "site"
    return normalized


def build_connection_alias(server_code: str, product_code: str | None) -> str:
    return f"{slugify_identifier(server_code, default='node')}-{infer_channel_name(product_code)}"
