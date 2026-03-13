import logging
import html
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.models import User, ChatMemory
from src.llm import generate_response
from src.config import SESSION_TIMEOUT_MINUTES, GROUP_MEMORY_LIMIT, PRIVATE_MEMORY_LIMIT

logger = logging.getLogger(__name__)
user_router = Router()

# In-memory session tracking for the 10-minute active window
# Dictionary maps (chat_id, user_id) -> last_active_datetime
active_sessions: dict[tuple[int, int], datetime] = {}

START_MESSAGE = """╭───────────────────⦿
│ ▸ ʜᴇʏ 愛 | 𝗥𝗨𝗛𝗜 𝗫 𝗤𝗡𝗥〆 
│ ▸ ɪ ᴀᴍ ˹ ᏒᏬᏂᎥ ꭙ ᏗᎥ ˼ 🧠 
├───────────────────⦿
│ ▸ ɪ ʜᴀᴠᴇ sᴘᴇᴄɪᴀʟ ғᴇᴀᴛᴜʀᴇs
│ ▸ ᴀᴅᴠᴀɴᴄᴇᴅ ᴀɪ ʙᴏᴛ
├───────────────────⦿
│ ▸ ʀᴇᴀʟ ɢɪʀʟ ᴘᴇʀsᴏɴᴀ
│ ▸ ᴍᴀsᴛɪ + ᴊᴏᴋᴇs + ᴄᴀʀᴇ
│ ▸ ɢʀᴏᴜᴘ + ᴘʀɪᴠᴀᴛᴇ sᴜᴘᴘᴏʀᴛ
│ ▸ ʀᴇᴍᴇᴍʙᴇʀs ᴇᴠᴇʀʏᴏɴᴇ
│ ▸ ɴᴀᴍᴇ sᴇ ʙᴜʟᴀᴛɪ ʜᴀɪ
│ ▸ 24x7 ᴏɴʟɪɴᴇ
├───────────────────⦿
│ sᴀʏ "ʀᴜʜɪ ᴊɪ" ᴛᴏ ᴄʜᴀᴛ
│ ᴍᴀᴅᴇ ʙʏ...@RUHI_VIG_QNR
╰───────────────────⦿"""

ABOUT_MESSAGE = """ʜᴇʏ ᴅᴇᴀʀ, 🥀
๏ ɪ ᴀᴍ ʀᴜʜɪ ᴊɪ — ʏᴏᴜʀ ᴀɪ ʙᴇsᴛ ғʀɪᴇɴᴅ
๏ ᴍᴀsᴛɪ • ᴊᴏᴋᴇs • ᴄᴀʀᴇ • ʟᴏᴠᴇ
๏ ᴘᴏᴡᴇʀᴇᴅ ʙʏ ʟʟᴀᴍᴀ 3.3 70ʙ
•── ⋅ ⋅ ────── ⋅ ────── ⋅ ⋅ ──•
๏ ɢʀᴏᴜᴘ: 20 ᴍsɢ ᴍᴇᴍᴏʀʏ (ᴀʟʟ ᴜsᴇʀs)
๏ ᴘʀɪᴠᴀᴛᴇ: 50 ᴍsɢ ᴍᴇᴍᴏʀʏ"""

HELP_MESSAGE = """╭───────────────────⦿
│ ʀᴜʜɪ ᴊɪ - ʜᴇʟᴘ
├───────────────────⦿
│ ʜᴏᴡ ᴛᴏ ᴄʜᴀᴛ:
│ sᴀʏ "ʀᴜʜɪ ᴊɪ" → 10 ᴍɪɴ sᴇssɪᴏɴ
│ ᴇx: "ʀᴜʜɪ ᴊɪ ᴋᴀɪsɪ ʜᴏ?"
├───────────────────⦿
│ /start - ʀᴇsᴛᴀʀᴛ ʙᴏᴛ
│ /about - ᴋɴᴏᴡ ᴀʙᴏᴜᴛ ᴍᴇ
│ /help - ʜᴏᴡ ᴛᴏ ᴜsᴇ
╰───────────────────⦿"""

async def ensure_user_exists(db_session: AsyncSession, from_user) -> str:
    """Ensures the user exists in the database and returns their name."""
    user_id = from_user.id
    name = from_user.first_name or "Dost"
    
    result = await db_session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(user_id=user_id, name=name)
        db_session.add(user)
        await db_session.commit()
    elif user.name != name:
        user.name = name
        await db_session.commit()
        
    return name

@user_router.message(CommandStart())
async def cmd_start(message: Message):
    """Handles the /start command."""
    async with AsyncSessionLocal() as db_session:
        await ensure_user_exists(db_session, message.from_user)
    await message.answer(START_MESSAGE)

@user_router.message(Command("about"))
async def cmd_about(message: Message):
    """Handles the /about command."""
    await message.answer(ABOUT_MESSAGE)

@user_router.message(Command("help"))
async def cmd_help(message: Message):
    """Handles the /help command."""
    await message.answer(HELP_MESSAGE)

@user_router.message(F.text)
async def handle_chat(message: Message):
    """Handles incoming text messages, triggers, and active sessions."""
    text = message.text
    chat_id = message.chat.id
    user_id = message.from_user.id
    is_private = message.chat.type == "private"
    
    # Trigger conditions
    trigger_keyword = "ruhi ji" in text.lower()
    is_reply = message.reply_to_message and message.reply_to_message.from_user.id == message.bot.id
    
    # Check active session
    now = datetime.utcnow()
    session_key = (chat_id, user_id)
    last_active = active_sessions.get(session_key)
    is_active_session = last_active and (now - last_active) < timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    
    # Decide if the bot should process this message
    if not (is_private or trigger_keyword or is_reply or is_active_session):
        return

    # Update active session timestamp
    active_sessions[session_key] = now
    
    # Notify user we are typing
    await message.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    async with AsyncSessionLocal() as db_session:
        # 1. Update/Ensure user profile
        user_name = await ensure_user_exists(db_session, message.from_user)
        
        # 2. Save incoming message to memory
        user_memory = ChatMemory(
            chat_id=chat_id,
            user_id=user_id,
            message_role="user",
            content=f"{user_name}: {text}" if not is_private else text
        )
        db_session.add(user_memory)
        
        # 3. Retrieve context history
        limit = PRIVATE_MEMORY_LIMIT if is_private else GROUP_MEMORY_LIMIT
        history_result = await db_session.execute(
            select(ChatMemory)
            .where(ChatMemory.chat_id == chat_id)
            .order_by(ChatMemory.timestamp.desc())
            .limit(limit)
        )
        history_records = history_result.scalars().all()
        
        # Reverse to chronological order
        history_records.reverse()
        
        context_messages = [
            {"role": rec.message_role, "content": rec.content} 
            for rec in history_records
        ]
        
        # 4. Generate LLM response
        chat_type_str = "Private Chat" if is_private else "Group Chat"
        bot_reply = await generate_response(db_session, user_name, chat_type_str, context_messages)
        
        # 5. Save bot reply to memory
        bot_memory = ChatMemory(
            chat_id=chat_id,
            user_id=message.bot.id,
            message_role="assistant",
            content=bot_reply
        )
        db_session.add(bot_memory)
        await db_session.commit()
        
    # 6. Send the reply
    await message.reply(bot_reply)
