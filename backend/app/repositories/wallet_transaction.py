from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.models.wallet_transaction import WalletTransaction


class WalletTransactionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, transaction: WalletTransaction) -> WalletTransaction:
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def list_for_wallet(self, wallet_id: str, *, limit: int = 20) -> list[WalletTransaction]:
        stmt = (
            select(WalletTransaction)
            .options(
                joinedload(WalletTransaction.payment),
                joinedload(WalletTransaction.billing_plan),
                joinedload(WalletTransaction.vpn_access),
            )
            .where(WalletTransaction.wallet_id == wallet_id)
            .order_by(desc(WalletTransaction.created_at))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique())
