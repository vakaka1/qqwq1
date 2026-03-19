from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ServerBase(BaseModel):
    code: str | None = None
    name: str
    country: str
    region: str | None = None
    host: str
    public_host: str | None = None
    scheme: str = "http"
    port: int
    public_port: int | None = None
    panel_path: str = ""
    connection_type: str = "three_x_ui_http"
    auth_mode: str = "username_password"
    username: str | None = None
    inbound_id: int | None = None
    client_flow: str | None = None
    is_active: bool = True
    is_trial_enabled: bool = True
    weight: int = Field(default=1, ge=1, le=100)
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=lambda: ["telegram-config", "site"])
    notes: str | None = None


class ServerCreate(ServerBase):
    auto_configure: bool = True
    password: str | None = None
    token: str | None = None


class ServerUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    country: str | None = None
    region: str | None = None
    host: str | None = None
    public_host: str | None = None
    scheme: str | None = None
    port: int | None = None
    public_port: int | None = None
    panel_path: str | None = None
    connection_type: str | None = None
    auth_mode: str | None = None
    username: str | None = None
    password: str | None = None
    token: str | None = None
    inbound_id: int | None = None
    client_flow: str | None = None
    auto_configure: bool | None = None
    is_active: bool | None = None
    is_trial_enabled: bool | None = None
    weight: int | None = Field(default=None, ge=1, le=100)
    tags: list[str] | None = None
    capabilities: list[str] | None = None
    notes: str | None = None


class InboundSummary(BaseModel):
    id: int
    remark: str | None = None
    protocol: str
    port: int | None = None
    enabled: bool | None = None


class ServerCountryLookupRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)


class ServerCountryLookupResponse(BaseModel):
    country: str
    resolved_ip: str


class ServerRead(ORMModel):
    id: str
    code: str
    name: str
    country: str
    region: str | None
    host: str
    public_host: str | None
    scheme: str
    port: int
    public_port: int | None
    panel_path: str
    connection_type: str
    auth_mode: str
    username: str | None
    inbound_id: int
    client_flow: str | None
    is_active: bool
    is_trial_enabled: bool
    weight: int
    health_status: str
    last_checked_at: datetime | None
    last_error: str | None
    tags: list[str]
    capabilities: list[str]
    notes: str | None
    connection_aliases: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    has_password: bool = False
    has_token: bool = False


class ServerTestResult(BaseModel):
    ok: bool
    status: str
    message: str
    version: str | None = None
    inbounds: list[InboundSummary] = Field(default_factory=list)


class ServerProbeResult(ServerTestResult):
    selected_inbound_id: int | None = None
    selected_inbound_remark: str | None = None
    recommended_public_host: str | None = None
    recommended_public_port: int | None = None
    recommended_client_flow: str | None = None
