import os
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

RAW_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_jYrNzuqFA0i8@ep-wispy-silence-a1lpucgo-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
)

# Properly strip ALL query params and fix scheme for asyncpg
_parsed = urlparse(RAW_DB_URL)
_clean = _parsed._replace(
    scheme="postgresql+asyncpg",
    query=""   # remove ?sslmode=require&channel_binding=require etc.
)
DATABASE_URL = urlunparse(_clean)

SESSION_TIMEOUT_MINUTES = 10
GROUP_MEMORY_LIMIT = 20
PRIVATE_MEMORY_LIMIT = 50
