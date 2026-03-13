import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.config import ADMIN_ID
from src.database import AsyncSessionLocal
from src.models import ApiKey

logger = logging.getLogger(__name__)
admin_router = Router()

# Filter to ensure only the admin can use these commands
admin_router.message.filter(F.from_user.id == ADMIN_ID)

@admin_router.message(Command("addkey"))
async def add_api_key(message: Message):
    """Adds a new Groq API key to the database."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: `/addkey <GROQ_API_KEY>`", parse_mode="Markdown")
        return

    api_key = args[1].strip()
    
    async with AsyncSessionLocal() as db_session:
        # Check if key already exists
        result = await db_session.execute(select(ApiKey).where(ApiKey.api_key == api_key))
        existing = result.scalar_one_or_none()
        
        if existing:
            await message.answer("This API key already exists in the database.")
            return

        # Add new key
        new_key = ApiKey(api_key=api_key)
        db_session.add(new_key)
        await db_session.commit()
        
        await message.answer(f"✅ Successfully added new API key. ID: {new_key.id}")

@admin_router.message(Command("listkeys"))
async def list_api_keys(message: Message):
    """Lists all configured Groq API keys and their statuses."""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(ApiKey).order_by(ApiKey.id))
        keys = result.scalars().all()
        
        if not keys:
            await message.answer("No API keys configured.")
            return

        response_lines = ["🔑 **Groq API Keys:**"]
        for k in keys:
            status = "🟢 Active" if k.is_active else "🔴 Inactive"
            masked_key = f"{k.api_key[:8]}...{k.api_key[-4:]}" if len(k.api_key) > 12 else "INVALID_LENGTH"
            response_lines.append(f"ID: `{k.id}` | Status: {status} | Usage: {k.usage_count} | Key: `{masked_key}`")
            
        await message.answer("\n".join(response_lines), parse_mode="Markdown")

@admin_router.message(Command("removekey"))
async def remove_api_key(message: Message):
    """Removes or disables an API key by ID."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Usage: `/removekey <ID>`", parse_mode="Markdown")
        return

    key_id = int(args[1])
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(ApiKey).where(ApiKey.id == key_id))
        key_record = result.scalar_one_or_none()
        
        if not key_record:
            await message.answer(f"API key with ID {key_id} not found.")
            return
            
        await db_session.delete(key_record)
        await db_session.commit()
        
        await message.answer(f"🗑️ Successfully removed API key ID: {key_id}")
