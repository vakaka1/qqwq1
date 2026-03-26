from __future__ import annotations

from pydantic import BaseModel, Field


class FreeKassaEndpointRead(BaseModel):
    method: str = "POST"
    url: str


class FreeKassaEndpointsRead(BaseModel):
    notification: FreeKassaEndpointRead
    success: FreeKassaEndpointRead
    failure: FreeKassaEndpointRead


class FreeKassaConfigRead(BaseModel):
    shop_id: int | None = None
    has_secret_word: bool = False
    has_api_key: bool = False
    has_secret_word_2: bool = False
    sbp_method_id: int = 42
    selected_method_label: str = "СБП"
    require_source_ip_check: bool = False
    allowed_ips: list[str] = Field(default_factory=list)
    endpoints: FreeKassaEndpointsRead
    notes: list[str] = Field(default_factory=list)


class FreeKassaNotificationRead(BaseModel):
    merchant_id: str
    amount: str
    intid: str
    merchant_order_id: str
    payer_email: str | None = None
    payer_phone: str | None = None
    currency_id: str | None = None
    payer_account: str | None = None
    commission: str | None = None
    source_ip: str | None = None
    custom_fields: dict[str, str] = Field(default_factory=dict)
