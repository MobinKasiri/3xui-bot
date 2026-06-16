"""Wallet ledger operations."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.models.transaction import (
    TX_ADMIN_CREDIT,
    TX_CONFIRMED,
    TX_PURCHASE,
    Transaction,
)

logger = logging.getLogger(__name__)


async def deduct(
    session: AsyncSession,
    user: User,
    amount: int,
    description: str,
    *,
    tx_type: str = TX_PURCHASE,
    plan_id: str | None = None,
    config_id: int | None = None,
    service_name: str | None = None,
    quantity: int = 1,
    discount_code: str | None = None,
    discount_amount: int = 0,
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
        payment_amount=amount,
        type=tx_type,
        description=description,
        plan_id=plan_id,
        config_id=config_id,
        service_name=service_name,
        quantity=quantity,
        payment_method="wallet",
        discount_code=discount_code,
        discount_amount=discount_amount,
        status=TX_CONFIRMED,
        confirmed_at=datetime.utcnow(),
    )


async def credit(
    session: AsyncSession,
    user_id: int,
    amount: int,
    description: str,
    *,
    tx_type: str = TX_ADMIN_CREDIT,
) -> Transaction:
    """Add balance to wallet and record confirmed transaction."""
    user = await User.get(session, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")
    new_balance = user.balance + amount
    await User.update(session, user_id, balance=new_balance)
    return await Transaction.create(
        session,
        user_id=user_id,
        amount=amount,
        payment_amount=amount,
        type=tx_type,
        description=description,
        status=TX_CONFIRMED,
        confirmed_at=datetime.utcnow(),
    )
