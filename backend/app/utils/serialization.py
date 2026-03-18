from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import quote


def parse_json_field(value):  # type: ignore[no-untyped-def]
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def dump_json(value: dict | list) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def datetime_to_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def encode_tag(value: str) -> str:
    return quote(value, safe="")

