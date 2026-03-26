from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel
from app.schemas.site import SiteConnectionPayload, SiteConnectionProbeResponse


class PaymentDomainSettingsPayload(BaseModel):
    domain: str = Field(min_length=3, max_length=255)

    @model_validator(mode="after")
    def validate_domain(self) -> "PaymentDomainSettingsPayload":
        self.domain = self.domain.strip()
        if not self.domain:
            raise ValueError("Укажите домен платежей")
        return self


class PaymentDomainProvisionRequest(BaseModel):
    connection: SiteConnectionPayload
    settings: PaymentDomainSettingsPayload


class PaymentDomainDeploymentPlanRead(BaseModel):
    payment_domain_code: str
    service_name: str
    domain: str
    public_url: str
    ssl_mode: str
    remote_root: str
    nginx_config_path: str
    backend_api_base_url: str
    deploy_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PaymentDomainRead(ORMModel):
    id: str
    code: str
    domain: str
    public_url: str | None
    server_access_mode: str
    server_host: str
    server_port: int
    server_username: str
    deployment_status: str
    ssl_mode: str
    last_deployed_at: datetime | None
    last_error: str | None
    connection_snapshot: dict = Field(default_factory=dict)
    deployment_snapshot: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    has_password: bool = False


class PaymentDomainDeleteRead(BaseModel):
    payment_domain_id: str
    domain: str
    deleted_from_admin: bool
    deleted_from_server: bool
    warnings: list[str] = Field(default_factory=list)
