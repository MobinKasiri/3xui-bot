"""
Admin router.

- /admin: dashboard.
- /stats, /users, /addbalance, /ban, /unban: existing tools.
- /addcode, /listcodes, /deletecode, /codestats: discount-code CRUD.
- /broadcast / /broadcast_send: bulk message.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.is_admin import IsAdmin
from app.bot.i18n import fa
from app.bot.utils.jalali import to_jalali, to_jalali_full
from app.bot.utils.persian import format_toman, to_persian_digits
from app.db.models import DiscountCode, DiscountUsage, Transaction, User, VPNConfig

logger = logging.getLogger(__name__)
router = Router(name="admin")


# ── dashboard ────────────────────────────────────────────────────────────────

async def _dashboard_text(session: AsyncSession, xui_service=None) -> str:
    today_users = await User.today_count(session)
    total_users = await User.count(session)
    active_configs = await VPNConfig.count_active(session)
    today_rev = int(await Transaction.today_revenue(session))
    total_rev = int(await Transaction.total_revenue(session))

    cpu = ram = "—"
    xray_state = "—"
    if xui_service:
        try:
            status = await xui_service.get_server_status()
            cpu = f"{status.cpu:.1f}"
            ram_pct = (status.mem_current / status.mem_total * 100) if status.mem_total else 0
            ram = f"{ram_pct:.1f}"
            xray_state = status.xray_state
        except Exception:
            logger.exception("Failed to get XUI server status")

    return fa.ADMIN_DASHBOARD.format(
        today_users=to_persian_digits(today_users),
        today_revenue=format_toman(today_rev),
        total_users=to_persian_digits(total_users),
        active_configs=to_persian_digits(active_configs),
        total_revenue=format_toman(total_rev),
        cpu=to_persian_digits(cpu),
        ram=to_persian_digits(ram),
        xray_state=xray_state,
    )


def _admin_keyboard() -> object:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 تراکنش‌های معلق", callback_data="admin:pending_txs")
    builder.button(text="👥 لیست کاربران", callback_data="admin:users:0")
    builder.button(text="🎟 کدهای تخفیف", callback_data="admin:codes")
    builder.button(text="📢 ارسال همگانی", callback_data="admin:broadcast_help")
    builder.button(text=fa.HOME, callback_data="main_menu")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


@router.message(IsAdmin(), Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession, **kwargs) -> None:
    xui_service = kwargs.get("xui_service")
    try:
        text = await _dashboard_text(session, xui_service)
    except Exception:
        logger.exception("Dashboard render failed")
        await message.answer(fa.ERRORS["general"])
        return
    await message.answer(text, reply_markup=_admin_keyboard())


@router.callback_query(F.data == "admin:dashboard")
async def cb_dashboard(
    callback: CallbackQuery, user: User, session: AsyncSession, **kwargs
) -> None:
    config = kwargs.get("config")
    if user.tg_id not in (config.bot.ADMINS if config else []):
        await callback.answer(fa.ERRORS["admin_only"], show_alert=True)
        return
    xui_service = kwargs.get("xui_service")
    try:
        text = await _dashboard_text(session, xui_service)
    except Exception:
        await callback.answer(fa.ERRORS["general"], show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=_admin_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=_admin_keyboard())
    await callback.answer()


@router.message(IsAdmin(), Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession, **kwargs) -> None:
    xui_service = kwargs.get("xui_service")
    text = await _dashboard_text(session, xui_service)
    await message.answer(text)


# ── user mgmt ────────────────────────────────────────────────────────────────

@router.message(IsAdmin(), Command("users"))
async def cmd_users(message: Message, session: AsyncSession, **kwargs) -> None:
    users = await User.get_all(session)
    lines = [f"<b>👥 کاربران ({to_persian_digits(len(users))} نفر)</b>\n"]
    for u in users[:20]:
        lines.append(
            f"• {u.full_name} (@{u.username or '—'}) — "
            f"ID: <code>{u.tg_id}</code> — موجودی: {format_toman(u.balance)} ت"
        )
    if len(users) > 20:
        lines.append(f"\n... و {to_persian_digits(len(users)-20)} کاربر دیگر")
    await message.answer("\n".join(lines))


@router.message(IsAdmin(), Command("addbalance"))
async def cmd_addbalance(message: Message, session: AsyncSession, **kwargs) -> None:
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("استفاده: /addbalance {user_id} {amount}")
        return
    try:
        target_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("آیدی و مبلغ باید عدد باشند.")
        return
    from app.bot.services.wallet import credit
    from app.db.models.transaction import TX_ADMIN_CREDIT
    try:
        await credit(session, target_id, amount, "شارژ توسط مدیر", tx_type=TX_ADMIN_CREDIT)
        target = await User.get(session, target_id)
        bal = target.balance if target else amount
        await message.answer(
            f"✅ موجودی کاربر {target_id} به اندازه {format_toman(amount)} تومان شارژ شد.\n"
            f"موجودی فعلی: {format_toman(bal)} تومان"
        )
        try:
            await message.bot.send_message(
                target_id,
                fa.WALLET_CHARGED.format(balance=format_toman(bal)),
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        await message.answer(f"❌ خطا: {e}")


@router.message(IsAdmin(), Command("ban"))
async def cmd_ban(message: Message, session: AsyncSession, **kwargs) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("استفاده: /ban {user_id}")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("آیدی باید عدد باشد.")
        return
    await User.update(session, target_id, is_banned=True)
    await message.answer(f"🚫 کاربر {target_id} مسدود شد.")


@router.message(IsAdmin(), Command("unban"))
async def cmd_unban(message: Message, session: AsyncSession, **kwargs) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("استفاده: /unban {user_id}")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("آیدی باید عدد باشد.")
        return
    await User.update(session, target_id, is_banned=False)
    await message.answer(f"✅ کاربر {target_id} رفع مسدودیت شد.")


# ── discount codes ───────────────────────────────────────────────────────────

def _parse_discount_value(raw: str) -> tuple[int | None, int | None]:
    """Return (percent, amount). E.g. '10%' -> (10, None); '5000t' -> (None, 5000)."""
    raw = raw.strip().lower()
    if raw.endswith("%"):
        try:
            return int(raw[:-1]), None
        except ValueError:
            return None, None
    if raw.endswith("t"):
        try:
            return None, int(raw[:-1])
        except ValueError:
            return None, None
    if raw.isdigit():
        return None, int(raw)
    return None, None


def _format_discount_value(code: DiscountCode) -> str:
    if code.discount_percent:
        return f"{to_persian_digits(code.discount_percent)}٪"
    if code.discount_amount:
        return f"{format_toman(code.discount_amount)} ت"
    return "—"


def _format_expires(code: DiscountCode) -> str:
    if code.expires_at is None:
        return "—"
    return to_jalali_full(code.expires_at)


@router.message(IsAdmin(), Command("addcode"))
async def cmd_addcode(message: Message, session: AsyncSession, **kwargs) -> None:
    parts = (message.text or "").split()
    if len(parts) < 5:
        await message.answer(fa.ADMIN_DISCOUNT_USAGE_HELP, parse_mode="HTML")
        return
    code_str = parts[1].strip().upper()
    percent, amount = _parse_discount_value(parts[2])
    if percent is None and amount is None:
        await message.answer(fa.ADMIN_DISCOUNT_USAGE_HELP, parse_mode="HTML")
        return
    try:
        max_uses = int(parts[3])
        expire_days = int(parts[4])
    except ValueError:
        await message.answer(fa.ADMIN_DISCOUNT_USAGE_HELP, parse_mode="HTML")
        return

    expires_at = datetime.utcnow() + timedelta(days=expire_days) if expire_days > 0 else None

    existing = await DiscountCode.get_by_code(session, code_str)
    if existing:
        await message.answer("❌ این کد قبلاً تعریف شده است.")
        return

    code = await DiscountCode.create(
        session,
        code=code_str,
        discount_percent=percent,
        discount_amount=amount,
        max_uses=max_uses,
        expires_at=expires_at,
        created_by=message.from_user.id,
    )
    await message.answer(
        fa.ADMIN_DISCOUNT_CREATED.format(
            code=code.code,
            value=_format_discount_value(code),
            max_uses=to_persian_digits(max_uses),
            expires=_format_expires(code),
        ),
        parse_mode="HTML",
    )


@router.message(IsAdmin(), Command("listcodes"))
async def cmd_listcodes(message: Message, session: AsyncSession, **kwargs) -> None:
    codes = await DiscountCode.list_active(session)
    if not codes:
        await message.answer("❌ هیچ کد تخفیف فعالی وجود ندارد.")
        return
    lines = [fa.ADMIN_DISCOUNT_LIST_HEADER]
    for code in codes:
        lines.append(
            fa.ADMIN_DISCOUNT_ROW.format(
                code=code.code,
                value=_format_discount_value(code),
                used=to_persian_digits(code.used_count),
                max_uses=to_persian_digits(code.max_uses),
                expires=_format_expires(code),
            )
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(IsAdmin(), Command("deletecode"))
async def cmd_deletecode(message: Message, session: AsyncSession, **kwargs) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("استفاده: /deletecode CODE")
        return
    code = await DiscountCode.get_by_code(session, parts[1])
    if not code:
        await message.answer(fa.ADMIN_DISCOUNT_NOT_FOUND)
        return
    await DiscountCode.deactivate(session, code.id)
    await message.answer(
        fa.ADMIN_DISCOUNT_DEACTIVATED.format(code=code.code), parse_mode="HTML"
    )


@router.message(IsAdmin(), Command("codestats"))
async def cmd_codestats(message: Message, session: AsyncSession, **kwargs) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("استفاده: /codestats CODE")
        return
    code = await DiscountCode.get_by_code(session, parts[1])
    if not code:
        await message.answer(fa.ADMIN_DISCOUNT_NOT_FOUND)
        return
    used = await DiscountUsage.count_for_code(session, code.id)
    state = "فعال" if code.is_active else "غیرفعال"
    await message.answer(
        fa.ADMIN_DISCOUNT_STATS.format(
            code=code.code,
            used=to_persian_digits(used),
            max_uses=to_persian_digits(code.max_uses),
            created=to_jalali(code.created_at) if code.created_at else "—",
            expires=_format_expires(code),
            state=state,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:codes")
async def cb_codes(
    callback: CallbackQuery, user: User, session: AsyncSession, **kwargs
) -> None:
    config = kwargs.get("config")
    if user.tg_id not in (config.bot.ADMINS if config else []):
        await callback.answer(fa.ERRORS["admin_only"], show_alert=True)
        return
    codes = await DiscountCode.list_active(session)
    if not codes:
        text = fa.ADMIN_DISCOUNT_LIST_HEADER + "\n❌ کد فعالی نیست.\n\n" + fa.ADMIN_DISCOUNT_USAGE_HELP
    else:
        lines = [fa.ADMIN_DISCOUNT_LIST_HEADER]
        for code in codes:
            lines.append(
                fa.ADMIN_DISCOUNT_ROW.format(
                    code=code.code,
                    value=_format_discount_value(code),
                    used=to_persian_digits(code.used_count),
                    max_uses=to_persian_digits(code.max_uses),
                    expires=_format_expires(code),
                )
            )
        lines.append("\n" + fa.ADMIN_DISCOUNT_USAGE_HELP)
        text = "\n".join(lines)

    builder = InlineKeyboardBuilder()
    builder.button(text=fa.BACK, callback_data="admin:dashboard")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


# ── broadcast ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast_help")
async def cb_broadcast_help(
    callback: CallbackQuery, user: User, **kwargs
) -> None:
    config = kwargs.get("config")
    if user.tg_id not in (config.bot.ADMINS if config else []):
        await callback.answer(fa.ERRORS["admin_only"], show_alert=True)
        return
    await callback.answer(
        "از دستور /broadcast_send <متن> برای ارسال همگانی استفاده کنید.",
        show_alert=True,
    )


@router.message(IsAdmin(), Command("broadcast_send"))
async def cmd_broadcast_send(message: Message, session: AsyncSession, **kwargs) -> None:
    text = (message.text or "").split(" ", 1)
    if len(text) < 2 or not text[1].strip():
        await message.answer("متن پیام خالی است.")
        return
    broadcast_text = text[1].strip()
    users = await User.get_all(session)
    sent = 0
    failed = 0
    status_msg = await message.answer(
        f"⏳ در حال ارسال به {to_persian_digits(len(users))} کاربر..."
    )
    for u in users:
        try:
            await message.bot.send_message(u.tg_id, broadcast_text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)
    await status_msg.edit_text(
        f"✅ ارسال همگانی کامل شد.\n"
        f"• موفق: {to_persian_digits(sent)}\n"
        f"• ناموفق: {to_persian_digits(failed)}"
    )


# ── pending txs ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:pending_txs")
async def cb_pending_txs(
    callback: CallbackQuery, user: User, session: AsyncSession, **kwargs
) -> None:
    config = kwargs.get("config")
    if user.tg_id not in (config.bot.ADMINS if config else []):
        await callback.answer(fa.ERRORS["admin_only"], show_alert=True)
        return
    txs = await Transaction.get_pending(session)
    if not txs:
        await callback.answer("هیچ تراکنش معلقی وجود ندارد.", show_alert=True)
        return
    lines = [f"💳 <b>تراکنش‌های معلق ({to_persian_digits(len(txs))})</b>\n"]
    for tx in txs[:10]:
        sign = "+" if tx.amount >= 0 else "-"
        lines.append(
            f"• <code>#{tx.id}</code> — کاربر {tx.tg_id if hasattr(tx, 'tg_id') else tx.user_id} — "
            f"{sign}{format_toman(abs(tx.amount))} ت — {tx.type}"
        )
    builder = InlineKeyboardBuilder()
    builder.button(text=fa.BACK, callback_data="admin:dashboard")
    builder.adjust(1)
    await callback.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:users:"))
async def cb_users_list(
    callback: CallbackQuery, user: User, session: AsyncSession, **kwargs
) -> None:
    config = kwargs.get("config")
    if user.tg_id not in (config.bot.ADMINS if config else []):
        await callback.answer(fa.ERRORS["admin_only"], show_alert=True)
        return

    page = int(callback.data.split(":")[-1])
    per_page = 10
    all_users = await User.get_all(session)
    start = page * per_page
    page_users = all_users[start:start + per_page]

    lines = [f"👥 <b>کاربران (صفحه {to_persian_digits(page+1)})</b>\n"]
    for u in page_users:
        lines.append(
            f"• <code>{u.tg_id}</code> — {u.full_name} (@{u.username or '—'}) — "
            f"{format_toman(u.balance)} ت"
        )

    builder = InlineKeyboardBuilder()
    if start > 0:
        builder.button(text="◀️ قبل", callback_data=f"admin:users:{page-1}")
    if start + per_page < len(all_users):
        builder.button(text="بعد ▶️", callback_data=f"admin:users:{page+1}")
    builder.button(text=fa.BACK, callback_data="admin:dashboard")
    builder.adjust(2, 1)
    await callback.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
    await callback.answer()
