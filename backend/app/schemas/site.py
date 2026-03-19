from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class SiteConnectionPayload(BaseModel):
    access_mode: Literal["root", "sudo"] = "root"
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=255)


class SiteSettingsPayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    managed_bot_id: str = Field(min_length=1, max_length=36)
    publish_mode: Literal["ip", "domain", "cloudflare_tunnel"] = "ip"
    domain: str | None = Field(default=None, max_length=255)
    proxy_port: int = Field(default=5000, ge=1025, le=65535)

    @model_validator(mode="after")
    def validate_domain_requirement(self) -> "SiteSettingsPayload":
        if self.publish_mode == "domain" and not (self.domain or "").strip():
            raise ValueError("Укажите домен сайта")
        if self.publish_mode != "domain":
            self.domain = None
        return self


class SiteTemplatePayload(BaseModel):
    key: str = Field(min_length=1, max_length=120)


class SiteProvisionRequest(BaseModel):
    connection: SiteConnectionPayload
    settings: SiteSettingsPayload
    template: SiteTemplatePayload


class SiteTemplateRead(BaseModel):
    key: str
    name: str
    filename: str
    description: str
    source_path: str
    placeholders: list[str] = Field(default_factory=list)
    is_default: bool = False


class SiteConnectionProbeResponse(BaseModel):
    ok: bool
    message: str
    hostname: str
    os_name: str
    os_version: str | None = None
    kernel: str
    machine: str | None = None
    python_version: str | None = None
    current_user: str
    home_dir: str
    is_root: bool
    sudo_available: bool
    package_manager: str | None = None


class SitePreviewRead(BaseModel):
    html: str
    telegram_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SiteRuntimeConfigRequest(BaseModel):
    site_code: str = Field(min_length=1, max_length=64)
    visitor_token: str = Field(min_length=8, max_length=64)
    client_ip: str | None = Field(default=None, max_length=128)
    user_agent: str | None = Field(default=None, max_length=512)


class SitePublicUrlReportRequest(BaseModel):
    site_code: str = Field(min_length=1, max_length=64)
    public_url: str = Field(min_length=12, max_length=255)


class SiteRuntimeConfigResponse(BaseModel):
    message: str
    site_code: str
    site_name: str
    access_id: str
    config_uri: str
    config_text: str
    expires_at: datetime
    expires_at_label: str
    server_name: str
    product_code: str


class SiteDeploymentPlanRead(BaseModel):
    site_code: str
    service_name: str
    template_name: str
    publish_mode: str
    server_name: str
    public_url: str
    proxy_port: int = 5000
    ssl_mode: str
    remote_root: str
    app_dir: str
    nginx_config_path: str | None = None
    systemd_unit_path: str
    cloudflare_unit_path: str | None = None
    cloudflare_url_file: str | None = None
    cloudflare_log_file: str | None = None
    deploy_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SiteManagedBotRead(BaseModel):
    id: str
    code: str
    name: str
    telegram_bot_username: str | None = None


class SiteRead(ORMModel):
    id: str
    code: str
    name: str
    publish_mode: str
    domain: str | None
    public_url: str | None
    template_key: str
    template_name: str
    server_access_mode: str
    server_host: str
    server_port: int
    server_username: str
    proxy_port: int
    deployment_status: str
    ssl_mode: str
    last_deployed_at: datetime | None
    last_error: str | None
    connection_snapshot: dict = Field(default_factory=dict)
    deployment_snapshot: dict = Field(default_factory=dict)
    managed_bot: SiteManagedBotRead
    created_at: datetime
    updated_at: datetime
    has_password: bool = False


class SiteDeleteRead(BaseModel):
    site_id: str
    site_name: str
    deleted_from_admin: bool
    deleted_from_server: bool
    warnings: list[str] = Field(default_factory=list)
