from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_wallet import UserWallet


class UserWalletRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, wallet_id: str) -> UserWallet | None:
        return self.db.get(UserWallet, wallet_id)

    def get_for_user_and_bot(self, telegram_user_id: int, managed_bot_id: str) -> UserWallet | None:
        stmt = select(UserWallet).where(
            UserWallet.telegram_user_id == telegram_user_id,
            UserWallet.managed_bot_id == managed_bot_id,
        )
        return self.db.scalar(stmt)

    def create(self, wallet: UserWallet) -> UserWallet:
        self.db.add(wallet)
        self.db.flush()
        return wallet

