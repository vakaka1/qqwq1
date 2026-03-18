from __future__ import annotations

from app.integrations.three_x_ui.client import ThreeXUIAdapter
from app.models.server import Server


def build_three_x_ui_adapter(server: Server) -> ThreeXUIAdapter:
    return ThreeXUIAdapter(server)

