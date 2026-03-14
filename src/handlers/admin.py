import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select
from src.config import ADMIN_ID
from src.database import AsyncSessionLocal
from src.models import ApiKey
from src.model_state import AVAILABLE_MODELS, get_model, get_model_label, set_model

logger = logging.getLogger(__name__)
admin_router = Router()
admin_router.message.filter(F.from_user.id == ADMIN_ID)
admin_router.callback_query.filter(F.from_user.id == ADMIN_ID)


# ── Helper: build model selector keyboard ────────────────────────────────
def model_keyboard() -> InlineKeyboardMarkup:
    active = get_model()
    buttons = []
    for key, label in AVAILABLE_MODELS.items():
        tick = "✅ " if key == active else ""
        buttons.append([InlineKeyboardButton(
            text=f"{tick}{label}",
            callback_data=f"setmodel:{key}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── /setmodel ─────────────────────────────────────────────────────────────
@admin_router.message(Command("setmodel"))
async def cmd_setmodel(message: Message):
    await message.answer(
        f"🤖 <b>Model Selector</b>\n\nCurrent: <b>{get_model_label()}</b>\n\nSelect karo:",
        parse_mode="HTML",
        reply_markup=model_keyboard()
    )


# ── Callback: button press ────────────────────────────────────────────────
@admin_router.callback_query(F.data.startswith("setmodel:"))
async def cb_setmodel(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    if set_model(key):
        await callback.message.edit_text(
            f"🤖 <b>Model Selector</b>\n\nCurrent: <b>{get_model_label()}</b>\n\nSelect karo:",
            parse_mode="HTML",
            reply_markup=model_keyboard()
        )
        await callback.answer(f"✅ Model changed to {get_model_label()}")
    else:
        await callback.answer("❌ Invalid model", show_alert=True)


# ── /addkey ───────────────────────────────────────────────────────────────
@admin_router.message(Command("addkey"))
async def add_api_key(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/addkey GROQ_API_KEY</code>", parse_mode="HTML")
        return
    api_key = args[1].strip()
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(ApiKey).where(ApiKey.api_key == api_key))
        if result.scalar_one_or_none():
            await message.answer("⚠️ Key already exists.")
            return
        db_session.add(ApiKey(api_key=api_key))
        await db_session.commit()
    await message.answer("✅ Groq API key added!")


# ── /listkeys ─────────────────────────────────────────────────────────────
@admin_router.message(Command("listkeys"))
async def list_api_keys(message: Message):
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(ApiKey).order_by(ApiKey.id))
        keys = result.scalars().all()
    if not keys:
        await message.answer("No Groq keys found.")
        return
    lines = ["🔑 <b>Groq API Keys:</b>"]
    for k in keys:
        status = "🟢" if k.is_active else "🔴"
        masked = f"{k.api_key[:8]}...{k.api_key[-4:]}"
        lines.append(f"{status} ID <code>{k.id}</code> | Used: {k.usage_count} | <code>{masked}</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ── /removekey ────────────────────────────────────────────────────────────
@admin_router.message(Command("removekey"))
async def remove_api_key(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Usage: <code>/removekey ID</code>", parse_mode="HTML")
        return
    key_id = int(args[1])
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(ApiKey).where(ApiKey.id == key_id))
        key_record = result.scalar_one_or_none()
        if not key_record:
            await message.answer(f"❌ Key ID {key_id} not found.")
            return
        await db_session.delete(key_record)
        await db_session.commit()
    await message.answer(f"🗑️ Key ID {key_id} removed.")
