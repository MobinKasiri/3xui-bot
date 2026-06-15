"""
Hourly: find configs ≥80% traffic usage, send warning.
Dedupes per (config_id, "80pct") bucket.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.i18n import fa
from app.bot.utils.persian import to_persian_digits
from app.db.models import VPNConfig
from app.db.models.notification_log import NotificationLog, NOTIF_TRAFFIC

logger = logging.getLogger(__name__)

TRAFFIC_WARN_PCT = 80.0


async def run_traffic_check(
    session_factory: async_sessionmaker,
    bot: Bot,
    plans: dict,
) -> None:
    logger.info("Running traffic usage check...")
    sent = 0

    async with session_factory() as session:
        configs = await VPNConfig.get_active(session)
        for config in configs:
            if config.traffic_limit_bytes == 0:
                continue
            pct = config.usage_percent
            if pct < TRAFFIC_WARN_PCT:
                continue

            bucket = "80pct"
            already = await NotificationLog.already_sent(session, config.id, NOTIF_TRAFFIC, bucket)
            if already:
                continue

            plan = plans.get(config.plan_key, {})
            plan_name = plan.get("name", config.plan_key or "سرویس")
            used_gb = config.traffic_used_gb
            total_gb = config.traffic_limit_gb

            text = fa.NOTIF_TRAFFIC_WARNING.format(
                used_gb=used_gb,
                total_gb=total_gb,
                pct=pct,
            )

            from aiogram.utils.keyboard import InlineKeyboardBuilder
            builder = InlineKeyboardBuilder()
            builder.button(text=fa.NOTIF_RENEW_BTN, callback_data=f"renewal:config:{config.id}")
            markup = builder.as_markup()

            try:
                await bot.send_message(config.user_id, text, parse_mode="HTML", reply_markup=markup)
                await NotificationLog.create(
                    session,
                    user_id=config.user_id,
                    config_id=config.id,
                    type=NOTIF_TRAFFIC,
                    bucket=bucket,
                )
                sent += 1
            except Exception as e:
                logger.debug(f"Failed to notify user {config.user_id}: {e}")

    logger.info(f"Traffic check complete. Sent {sent} warnings.")
