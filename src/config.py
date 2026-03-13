import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# Database configuration
# Convert standard postgresql:// to postgresql+asyncpg:// for SQLAlchemy async support
RAW_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_jYrNzuqFA0i8@ep-wispy-silence-a1lpucgo-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
)
if RAW_DB_URL.startswith("postgresql://"):
    DATABASE_URL = RAW_DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = RAW_DB_URL

# Session configuration
SESSION_TIMEOUT_MINUTES = 10
GROUP_MEMORY_LIMIT = 20
PRIVATE_MEMORY_LIMIT = 50
