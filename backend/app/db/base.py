from __future__ import annotations

from app.db.base_class import Base


from app.models.admin import Admin  # noqa: E402,F401
from app.models.audit_log import AuditLog  # noqa: E402,F401
from app.models.billing_plan import BillingPlan  # noqa: E402,F401
from app.models.bot_user import BotUser  # noqa: E402,F401
from app.models.managed_bot import ManagedBot  # noqa: E402,F401
from app.models.payment import Payment  # noqa: E402,F401
from app.models.server import Server  # noqa: E402,F401
from app.models.site import Site  # noqa: E402,F401
from app.models.system_settings import SystemSettings  # noqa: E402,F401
from app.models.telegram_user import TelegramUser  # noqa: E402,F401
from app.models.user_wallet import UserWallet  # noqa: E402,F401
from app.models.vpn_access import VpnAccess  # noqa: E402,F401
from app.models.wallet_transaction import WalletTransaction  # noqa: E402,F401
