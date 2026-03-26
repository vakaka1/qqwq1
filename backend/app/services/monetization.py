from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing_plan import BillingPlan
from app.models.enums import UserStatus
from app.models.payment import Payment
from app.models.telegram_user import TelegramUser
from app.models.user_wallet import UserWallet
from app.models.wallet_transaction import WalletTransaction
from app.repositories.billing_plan import BillingPlanRepository
from app.repositories.managed_bot import ManagedBotRepository
from app.repositories.payment import PaymentRepository
from app.repositories.telegram_user import TelegramUserRepository
from app.repositories.user_wallet import UserWalletRepository
from app.repositories.vpn_access import VpnAccessRepository
from app.repositories.wallet_transaction import WalletTransactionRepository
from app.schemas.monetization import (
    BillingPlanCreate,
    BillingPlanRead,
    BillingPlanUpdate,
    BotBillingPlanRead,
    BotBillingRead,
    BotPaymentRead,
    BotPlanPurchaseResponse,
    BotTopUpRequest,
    MonetizationSummaryRead,
    PaymentRead,
    WalletRead,
    WalletTransactionRead,
)
from app.services.audit import AuditService
from app.services.bot_messenger import BotMessengerService
from app.services.exceptions import ServiceError
from app.services.freekassa import FreeKassaService
from app.services.system_settings import load_effective_system_settings


class MonetizationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.bots = ManagedBotRepository(db)
        self.users = TelegramUserRepository(db)
        self.wallets = UserWalletRepository(db)
        self.plans = BillingPlanRepository(db)
        self.payments = PaymentRepository(db)
        self.accesses = VpnAccessRepository(db)
        self.transactions = WalletTransactionRepository(db)
        self.audit = AuditService(db)
        self.bot_messenger = BotMessengerService()
        self.freekassa = FreeKassaService()

    @staticmethod
    def format_kopecks(value: int) -> str:
        sign = "-" if value < 0 else ""
        normalized = abs(int(value))
        return f"{sign}{normalized // 100}.{normalized % 100:02d}"

    @staticmethod
    def format_amount_label(value: int) -> str:
        rubles = value / 100
        if value % 100 == 0:
            return str(int(rubles))
        return f"{rubles:.2f}"

    @staticmethod
    def duration_label(hours: int) -> str:
        if hours % (24 * 30) == 0:
            months = hours // (24 * 30)
            return f"{months} мес."
        if hours % 24 == 0:
            days = hours // 24
            return f"{days} дн."
        return f"{hours} ч."

    def _resolve_managed_bot(self, bot_code: str):
        managed_bot = self.bots.get_by_code(bot_code)
        if not managed_bot or not managed_bot.is_active:
            raise ServiceError("Активный бот не найден", 404)
        return managed_bot

    def _get_or_create_user(self, telegram_user_id: int) -> TelegramUser:
        user = self.users.get_by_telegram_id(telegram_user_id)
        if user:
            return user

        user = TelegramUser(
            telegram_user_id=telegram_user_id,
            status=UserStatus.NEW.value,
        )
        self.users.create(user)
        self.audit.log(
            actor_type="bot",
            actor_id=str(telegram_user_id),
            event_type="telegram_user_created",
            entity_type="telegram_user",
            entity_id=str(telegram_user_id),
            message=f"Создан Telegram-пользователь {telegram_user_id} через монетизацию",
        )
        return user

    def get_or_create_wallet(self, user: TelegramUser, managed_bot) -> UserWallet:
        wallet = self.wallets.get_for_user_and_bot(user.id, managed_bot.id)
        if wallet:
            if wallet.trial_used_at is None:
                latest_trial = self.accesses.get_latest_trial_for_telegram_user_and_bot(user.telegram_user_id, managed_bot.id)
                if latest_trial:
                    wallet.trial_used_at = latest_trial.activated_at
                    wallet.trial_started_at = latest_trial.activated_at
                    wallet.trial_ends_at = latest_trial.expiry_at
                    self.db.flush()
            return wallet

        latest_trial = self.accesses.get_latest_trial_for_telegram_user_and_bot(user.telegram_user_id, managed_bot.id)
        wallet = UserWallet(
            telegram_user_id=user.id,
            managed_bot_id=managed_bot.id,
            balance_kopecks=0,
            trial_used_at=latest_trial.activated_at if latest_trial else None,
            trial_started_at=latest_trial.activated_at if latest_trial else None,
            trial_ends_at=latest_trial.expiry_at if latest_trial else None,
        )
        self.wallets.create(wallet)
        return wallet

    def _require_plan(self, plan_id: str, *, managed_bot_id: str | None = None) -> BillingPlan:
        plan = self.plans.get(plan_id)
        if not plan:
            raise ServiceError("Тариф не найден", 404)
        if managed_bot_id and plan.managed_bot_id != managed_bot_id:
            raise ServiceError("Тариф не относится к выбранному боту", 404)
        return plan

    def _to_plan_read(self, plan: BillingPlan) -> BillingPlanRead:
        return BillingPlanRead.model_validate(plan)

    def _to_bot_plan_read(self, plan: BillingPlan) -> BotBillingPlanRead:
        return BotBillingPlanRead(
            id=plan.id,
            name=plan.name,
            description=plan.description,
            duration_hours=plan.duration_hours,
            duration_label=self.duration_label(plan.duration_hours),
            price_kopecks=plan.price_kopecks,
            price_rub=self.format_kopecks(plan.price_kopecks),
            sort_order=plan.sort_order,
        )

    def _to_wallet_read(self, wallet: UserWallet) -> WalletRead:
        recent_transactions = [
            WalletTransactionRead.model_validate(item)
            for item in self.transactions.list_for_wallet(wallet.id, limit=10)
        ]
        return WalletRead(
            wallet_id=wallet.id,
            balance_kopecks=wallet.balance_kopecks,
            balance_rub=self.format_kopecks(wallet.balance_kopecks),
            trial_used=wallet.trial_used_at is not None,
            trial_started_at=wallet.trial_started_at,
            trial_ends_at=wallet.trial_ends_at,
            recent_transactions=recent_transactions,
        )

    def _to_payment_read(self, payment: Payment) -> PaymentRead:
        return PaymentRead.model_validate(payment)

    def _build_telegram_payer_email(self, telegram_user_id: int) -> str:
        return f"telegram-user-{telegram_user_id}@example.com"

    @staticmethod
    def _payment_method_label(value: str | None) -> str:
        if not value:
            return "Онлайн-оплата"
        labels = {"sbp": "СБП"}
        return labels.get(value.lower(), value.upper())

    def _create_wallet_transaction(
        self,
        *,
        wallet: UserWallet,
        amount_kopecks: int,
        operation_type: str,
        description: str,
        payment_id: str | None = None,
        billing_plan_id: str | None = None,
        vpn_access_id: str | None = None,
        payload: dict | None = None,
    ) -> WalletTransaction:
        transaction = WalletTransaction(
            wallet_id=wallet.id,
            payment_id=payment_id,
            billing_plan_id=billing_plan_id,
            vpn_access_id=vpn_access_id,
            amount_kopecks=amount_kopecks,
            balance_after_kopecks=wallet.balance_kopecks,
            currency="RUB",
            operation_type=operation_type,
            description=description,
            payload=payload or {},
        )
        return self.transactions.create(transaction)

    def get_summary(self) -> MonetizationSummaryRead:
        recent_payments = [self._to_payment_read(item) for item in self.payments.list_recent(limit=10)]
        active_plans = 0
        total_plans = 0
        for bot in self.bots.list():
            plans = self.plans.list_for_bot(bot.id)
            total_plans += len(plans)
            active_plans += sum(1 for item in plans if item.is_active)

        paid_total_kopecks = self.payments.total_paid_kopecks()
        return MonetizationSummaryRead(
            total_plans=total_plans,
            active_plans=active_plans,
            pending_payments=self.payments.count_by_status("pending") + self.payments.count_by_status("created"),
            paid_payments=self.payments.count_by_status("paid"),
            paid_total_kopecks=paid_total_kopecks,
            paid_total_rub=self.format_kopecks(paid_total_kopecks),
            recent_payments=recent_payments,
        )

    def list_plans(self, *, managed_bot_id: str | None = None, active_only: bool = False) -> list[BillingPlanRead]:
        plans: list[BillingPlan] = []
        if managed_bot_id:
            plans = self.plans.list_for_bot(managed_bot_id, active_only=active_only)
        else:
            for bot in self.bots.list():
                plans.extend(self.plans.list_for_bot(bot.id, active_only=active_only))
        return [self._to_plan_read(item) for item in plans]

    def create_plan(self, payload: BillingPlanCreate, *, actor_id: str | None = None) -> BillingPlanRead:
        managed_bot = self.bots.get(payload.managed_bot_id)
        if not managed_bot:
            raise ServiceError("Бот не найден", 404)
        plan = BillingPlan(**payload.model_dump())
        self.plans.create(plan)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="billing_plan_created",
            entity_type="billing_plan",
            entity_id=plan.id,
            message=f"Создан тариф {plan.name}",
            payload=payload.model_dump(),
        )
        self.db.commit()
        self.db.refresh(plan)
        return self._to_plan_read(plan)

    def update_plan(self, plan_id: str, payload: BillingPlanUpdate, *, actor_id: str | None = None) -> BillingPlanRead:
        plan = self._require_plan(plan_id)
        changes = payload.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(plan, key, value)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="billing_plan_updated",
            entity_type="billing_plan",
            entity_id=plan.id,
            message=f"Обновлен тариф {plan.name}",
            payload=changes,
        )
        self.db.commit()
        self.db.refresh(plan)
        return self._to_plan_read(plan)

    def delete_plan(self, plan_id: str, *, actor_id: str | None = None) -> None:
        plan = self._require_plan(plan_id)
        self.audit.log(
            actor_type="admin",
            actor_id=actor_id,
            event_type="billing_plan_deleted",
            entity_type="billing_plan",
            entity_id=plan.id,
            message=f"Удален тариф {plan.name}",
            payload={"name": plan.name},
        )
        try:
            self.plans.delete(plan)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ServiceError("Тариф уже использовался в платежах или списаниях, удаление недоступно", 409) from exc

    def get_bot_billing(self, *, bot_code: str, telegram_user_id: int) -> BotBillingRead:
        managed_bot = self._resolve_managed_bot(bot_code)
        user = self._get_or_create_user(telegram_user_id)
        wallet = self.get_or_create_wallet(user, managed_bot)
        active_plans = self.plans.list_for_bot(managed_bot.id, active_only=True)
        self.db.commit()
        return BotBillingRead(
            bot_code=managed_bot.code,
            wallet=self._to_wallet_read(wallet),
            plans=[self._to_bot_plan_read(item) for item in active_plans],
        )

    def create_top_up_payment(self, payload: BotTopUpRequest) -> BotPaymentRead:
        managed_bot = self._resolve_managed_bot(payload.bot_code)
        user = self._get_or_create_user(payload.telegram_user_id)
        wallet = self.get_or_create_wallet(user, managed_bot)

        plan = None
        amount_kopecks = payload.amount_kopecks
        if payload.plan_id:
            plan = self._require_plan(payload.plan_id, managed_bot_id=managed_bot.id)
            if not plan.is_active:
                raise ServiceError("Тариф отключен", 409)
            if payload.cover_shortfall_for_plan:
                amount_kopecks = max(plan.price_kopecks - wallet.balance_kopecks, 0)
                if amount_kopecks <= 0:
                    raise ServiceError("Баланс уже покрывает стоимость тарифа", 409)
            elif amount_kopecks is None:
                amount_kopecks = plan.price_kopecks

        if amount_kopecks is None or amount_kopecks <= 0:
            raise ServiceError("Сумма пополнения должна быть больше нуля", 400)

        payment_id = str(uuid4())
        payment = Payment(
            id=payment_id,
            merchant_order_id=payment_id,
            redirect_token=secrets.token_urlsafe(32),
            telegram_user_id=user.id,
            managed_bot_id=managed_bot.id,
            wallet_id=wallet.id,
            billing_plan_id=plan.id if plan else None,
            amount_kopecks=amount_kopecks,
            currency="RUB",
            status="pending",
            provider="freekassa",
            payment_method="sbp",
            purpose="balance_top_up",
            provider_response={},
            notification_payload={},
        )
        self.payments.create(payment)
        self.audit.log(
            actor_type="bot",
            actor_id=str(user.telegram_user_id),
            event_type="top_up_payment_created",
            entity_type="payment",
            entity_id=payment.id,
            message=f"Создано пополнение баланса на {self.format_amount_label(amount_kopecks)} RUB",
            payload={
                "bot_code": managed_bot.code,
                "billing_plan_id": plan.id if plan else None,
                "amount_kopecks": amount_kopecks,
            },
        )
        buyer_email = self._build_telegram_payer_email(user.telegram_user_id)
        effective_settings = load_effective_system_settings(self.db)
        payment_redirect_url = self.freekassa.build_payment_redirect_url(
            payment.redirect_token,
            public_app_url=effective_settings.freekassa_public_url or effective_settings.public_app_url,
        )
        payment.payer_email = buyer_email
        payment.provider_response = {
            "checkout": "freekassa_api_redirect",
            "payment_redirect_url": payment_redirect_url,
            "provider_payment_url": None,
        }
        self.db.commit()
        return BotPaymentRead(
            payment_id=payment.id,
            amount_kopecks=payment.amount_kopecks,
            amount_rub=self.format_kopecks(payment.amount_kopecks),
            payment_url=payment_redirect_url,
            status=payment.status,
            provider=payment.provider,
            payment_method=payment.payment_method,
        )

    def prepare_payment_redirect(self, payment_token: str, *, source_ip: str | None) -> str:
        payment = self.payments.get_by_redirect_token(payment_token)
        if not payment:
            raise ServiceError("Платеж не найден", 404)
        if payment.status == "paid":
            raise ServiceError("Платеж уже оплачен", 409)
        if payment.provider_payment_url:
            return payment.provider_payment_url

        buyer_email = payment.payer_email or self._build_telegram_payer_email(payment.telegram_user.telegram_user_id)
        provider_response = self.freekassa.create_payment(
            merchant_order_id=payment.merchant_order_id,
            amount_kopecks=payment.amount_kopecks,
            payment_method_id=payment.payment_method,
            payer_email=buyer_email,
            payer_ip=source_ip,
        )
        provider_payment_url = str(provider_response.get("location") or "").strip()
        if not provider_payment_url:
            raise ServiceError("FreeKassa не вернула ссылку на оплату", 502)

        external_order_id = provider_response.get("orderId")
        payment.status = "created"
        payment.source_ip = source_ip
        payment.payer_email = buyer_email
        payment.external_order_id = str(external_order_id) if external_order_id is not None else payment.external_order_id
        payment.provider_payment_url = provider_payment_url
        payment.provider_response = {
            **provider_response,
            "checkout": "freekassa_api",
            "provider_payment_url": provider_payment_url,
            "payer_ip": source_ip,
        }
        self.audit.log(
            actor_type="bot",
            actor_id=str(payment.telegram_user.telegram_user_id),
            event_type="top_up_payment_redirect_prepared",
            entity_type="payment",
            entity_id=payment.id,
            message="Создан заказ FreeKassa и подготовлен redirect на оплату",
            payload={"source_ip": source_ip, "provider_response": payment.provider_response},
        )
        self.db.commit()
        return payment.provider_payment_url

    def prepare_payment_page(self, payment_token: str, *, source_ip: str | None) -> dict[str, object]:
        payment = self.payments.get_by_redirect_token(payment_token)
        if not payment:
            raise ServiceError("Платеж не найден", 404)

        if payment.status != "paid":
            self.prepare_payment_redirect(payment_token, source_ip=source_ip)
            payment = self.payments.get_by_redirect_token(payment_token) or payment

        effective_settings = load_effective_system_settings(self.db)
        brand_name = (effective_settings.app_name or "").strip() or (payment.managed_bot.name if payment.managed_bot else "Оплата")
        return {
            "brand_name": brand_name,
            "order_id": payment.merchant_order_id,
            "amount_rub": self.format_kopecks(payment.amount_kopecks),
            "payment_url": None if payment.status == "paid" else payment.provider_payment_url,
            "payment_method_label": self._payment_method_label(payment.payment_method),
            "bot_name": payment.managed_bot.name if payment.managed_bot else None,
            "plan_name": payment.billing_plan.name if payment.billing_plan else None,
            "is_paid": payment.status == "paid",
        }

    def apply_successful_payment_notification(self, notification) -> Payment:
        payment = self.payments.get_by_merchant_order_id(notification.merchant_order_id)
        if not payment:
            raise ServiceError("Платеж не найден", 404)

        expected_amount = self.format_kopecks(payment.amount_kopecks)
        actual_amount = notification.amount
        try:
            actual_kopecks = int((Decimal(actual_amount) * Decimal("100")).quantize(Decimal("1")))
        except (InvalidOperation, ValueError) as exc:
            raise ServiceError("Некорректная сумма платежа", 400) from exc

        if actual_kopecks != payment.amount_kopecks:
            raise ServiceError(
                f"Сумма платежа не совпадает: ожидалось {expected_amount}, получено {actual_amount}",
                400,
            )

        if payment.status != "paid":
            wallet = payment.wallet or self.wallets.get(payment.wallet_id)
            if wallet is None:
                raise ServiceError("Кошелек пользователя не найден", 404)
            wallet.balance_kopecks += payment.amount_kopecks
            payment.status = "paid"
            payment.external_payment_id = notification.intid
            payment.payer_email = notification.payer_email or payment.payer_email
            payment.paid_at = datetime.now(timezone.utc)
            payment.notification_payload = notification.model_dump()
            self._create_wallet_transaction(
                wallet=wallet,
                amount_kopecks=payment.amount_kopecks,
                operation_type="top_up",
                description=f"Пополнение баланса через FreeKassa ({self.format_amount_label(payment.amount_kopecks)} RUB)",
                payment_id=payment.id,
                billing_plan_id=payment.billing_plan_id,
                payload={"provider": payment.provider, "payment_method": payment.payment_method},
            )
            self.audit.log(
                actor_type="payment_gateway",
                actor_id=notification.source_ip,
                event_type="payment_marked_paid",
                entity_type="payment",
                entity_id=payment.id,
                message=f"Платеж {payment.id} успешно оплачен",
                payload=notification.model_dump(),
            )
            self.db.commit()

            self.bot_messenger.send_message_sync(
                payment.managed_bot.code,
                payment.telegram_user.telegram_user_id,
                (
                    "Баланс пополнен\n\n"
                    f"Сумма: {self.format_amount_label(payment.amount_kopecks)} RUB\n"
                    f"Новый баланс: {self.format_amount_label(wallet.balance_kopecks)} RUB\n\n"
                    "Теперь можно продлить доступ через меню бота."
                ),
                parse_mode=None,
            )

        return payment

    def purchase_plan_from_balance(self, *, bot_code: str, telegram_user_id: int, plan_id: str) -> BotPlanPurchaseResponse:
        managed_bot = self._resolve_managed_bot(bot_code)
        user = self._get_or_create_user(telegram_user_id)
        wallet = self.get_or_create_wallet(user, managed_bot)
        plan = self._require_plan(plan_id, managed_bot_id=managed_bot.id)
        if not plan.is_active:
            raise ServiceError("Тариф отключен", 409)
        if wallet.balance_kopecks < plan.price_kopecks:
            shortfall = plan.price_kopecks - wallet.balance_kopecks
            raise ServiceError(
                f"Недостаточно средств на балансе. Нужно пополнить еще на {self.format_amount_label(shortfall)} RUB",
                409,
            )

        from app.services.vpn_accesses import VpnAccessService

        access_service = VpnAccessService(self.db)
        access = access_service.ensure_paid_access_for_user(
            managed_bot=managed_bot,
            user=user,
            duration_hours=plan.duration_hours,
        )
        wallet.balance_kopecks -= plan.price_kopecks
        self._create_wallet_transaction(
            wallet=wallet,
            amount_kopecks=-plan.price_kopecks,
            operation_type="purchase",
            description=f"Покупка тарифа {plan.name}",
            billing_plan_id=plan.id,
            vpn_access_id=access.id,
            payload={
                "duration_hours": plan.duration_hours,
                "bot_code": managed_bot.code,
            },
        )
        self.audit.log(
            actor_type="bot",
            actor_id=str(user.telegram_user_id),
            event_type="billing_plan_purchased",
            entity_type="billing_plan",
            entity_id=plan.id,
            message=f"Пользователь {user.telegram_user_id} купил тариф {plan.name}",
            payload={
                "bot_code": managed_bot.code,
                "vpn_access_id": access.id,
                "price_kopecks": plan.price_kopecks,
                "duration_hours": plan.duration_hours,
            },
        )
        self.db.commit()
        self.db.refresh(access)
        return BotPlanPurchaseResponse(
            message="Доступ продлен",
            bot_code=managed_bot.code,
            access_id=access.id,
            config_uri=access.config_uri or "",
            config_text=access.config_text or "",
            expires_at=access.expiry_at,
            server_name=access.server.name,
            charged_kopecks=plan.price_kopecks,
            charged_rub=self.format_kopecks(plan.price_kopecks),
            balance_kopecks=wallet.balance_kopecks,
            balance_rub=self.format_kopecks(wallet.balance_kopecks),
        )
