import asyncio
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from src.config import BOT_TOKEN
from src.database import init_db
from src.handlers.admin import admin_router
from src.handlers.user import user_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ── Fake Web Server (Render ke liye) ─────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Ruhi Ji Bot is alive! \xf0\x9f\xa5\x80")

    def log_message(self, format, *args):
        pass  # Suppress request logs


def run_web_server():
    port = 10000  # Render default port
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Fake web server running on port {port}")
    server.serve_forever()


# ── Bot ───────────────────────────────────────────────────────────────────
async def main():
    logger.info("Starting Ruhi Ji Bot...")

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing!")
        return

    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(user_router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Bot is polling...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Critical error: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    # Web server alag thread mein chalao
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
