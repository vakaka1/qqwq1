from __future__ import annotations

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_bots: int
    active_bots: int
    total_servers: int
    active_servers: int
    active_clients: int
    test_clients: int
    expired_accesses: int
    total_users: int
