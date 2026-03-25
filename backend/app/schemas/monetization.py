from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class BillingPlanBase(BaseModel):
    managed_bot_id: str
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    duration_hours: int = Field(ge=1, le=24 * 365)
    price_kopecks: int = Field(ge=100, le=10_000_000)
    sort_order: int = Field(default=100, ge=0, le=10_000)
    is_active: bool = True


class BillingPlanCreate(BillingPlanBase):
    pass


class BillingPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    duration_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    price_kopecks: int | None = Field(default=None, ge=100, le=10_000_000)
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    is_active: bool | None = None


class BillingPlanRead(ORMModel):
    id: str
    managed_bot_id: str
    name: str
    description: str | None
    duration_hours: int
    price_kopecks: int
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BotBillingPlanRead(BaseModel):
    id: str
    name: str
    description: str | None = None
    duration_hours: int
    duration_label: str
    price_kopecks: int
    price_rub: str
    sort_order: int


class WalletTransactionRead(ORMModel):
    id: str
    payment_id: str | None
    billing_plan_id: str | None
    vpn_access_id: str | None
    amount_kopecks: int
    balance_after_kopecks: int
    currency: str
    operation_type: str
    description: str
    payload: dict
    created_at: datetime
    updated_at: datetime


class WalletRead(BaseModel):
    wallet_id: str
    balance_kopecks: int
    balance_rub: str
    trial_used: bool
    trial_started_at: datetime | None = None
    trial_ends_at: datetime | None = None
    recent_transactions: list[WalletTransactionRead] = Field(default_factory=list)


class PaymentRead(ORMModel):
    id: str
    merchant_order_id: str
    amount_kopecks: int
    currency: str
    status: str
    provider: str
    payment_method: str
    purpose: str
    source_ip: str | None
    payer_email: str | None
    external_order_id: str | None
    external_payment_id: str | None
    provider_payment_url: str | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BotBillingRead(BaseModel):
    bot_code: str
    wallet: WalletRead
    plans: list[BotBillingPlanRead] = Field(default_factory=list)


class BotTopUpRequest(BaseModel):
    bot_code: str
    telegram_user_id: int
    plan_id: str | None = None
    amount_kopecks: int | None = Field(default=None, ge=100, le=10_000_000)
    cover_shortfall_for_plan: bool = True


class BotPaymentRead(BaseModel):
    payment_id: str
    amount_kopecks: int
    amount_rub: str
    payment_url: str
    status: str
    provider: str
    payment_method: str


class BotPlanPurchaseRequest(BaseModel):
    bot_code: str
    telegram_user_id: int
    plan_id: str


class BotPlanPurchaseResponse(BaseModel):
    message: str
    bot_code: str
    access_id: str
    config_uri: str
    config_text: str
    expires_at: datetime
    server_name: str
    charged_kopecks: int
    charged_rub: str
    balance_kopecks: int
    balance_rub: str


class MonetizationSummaryRead(BaseModel):
    total_plans: int
    active_plans: int
    pending_payments: int
    paid_payments: int
    paid_total_kopecks: int
    paid_total_rub: str
    recent_payments: list[PaymentRead] = Field(default_factory=list)
