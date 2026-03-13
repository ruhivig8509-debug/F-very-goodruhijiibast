import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

# asyncpg does NOT support ?sslmode=require — strip it out
RAW_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_jYrNzuqFA0i8@ep-wispy-silence-a1lpucgo-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
)

# Replace scheme and remove sslmode param
DATABASE_URL = RAW_DB_URL \
    .replace("postgresql://", "postgresql+asyncpg://", 1) \
    .replace("?sslmode=require", "") \
    .replace("&sslmode=require", "")

SESSION_TIMEOUT_MINUTES = 10
GROUP_MEMORY_LIMIT = 20
PRIVATE_MEMORY_LIMIT = 50
