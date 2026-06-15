"""Wallet ledger operations."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.models.transaction import (
    Transaction,
    TX_PURCHASE, TX_WALLET_TOPUP, TX_ADMIN_CREDIT,
    TX_CONFIRMED, TX_PENDING,
)

logger = logging.getLogger(__name__)


async def deduct(
    session: AsyncSession,
    user: User,
    amount: int,
    description: str,
    tx_type: str = TX_PURCHASE,
    plan_key: str | None = None,
    config_id: int | None = None,
) -> Transaction:
    """Deduct balance from wallet. Raises ValueError if insufficient."""
    if user.balance < amount:
        raise ValueError(f"Insufficient balance: {user.balance} < {amount}")
    new_balance = user.balance - amount
    await User.update(session, user.tg_id, balance=new_balance)
    user.balance = new_balance
    return await Transaction.create(
        session,
        user_id=user.tg_id,
        amount=-amount,
        type=tx_type,
        description=description,
        plan_key=plan_key,
        config_id=config_id,
        status=TX_CONFIRMED,
    )


async def credit(
    session: AsyncSession,
    user_id: int,
    amount: int,
    description: str,
    tx_type: str = TX_ADMIN_CREDIT,
) -> Transaction:
    """Add balance to wallet and record confirmed transaction."""
    from app.db.models.user import User as U
    user = await U.get(session, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")
    new_balance = user.balance + amount
    await U.update(session, user_id, balance=new_balance)
    return await Transaction.create(
        session,
        user_id=user_id,
        amount=amount,
        type=tx_type,
        description=description,
        status=TX_CONFIRMED,
    )
