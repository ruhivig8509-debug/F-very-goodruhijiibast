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


# ── Fake Web Server ───────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write("Ruhi Ji Bot is alive! \U0001f940".encode())

    def log_message(self, format, *args):
        pass  # Suppress noisy request logs


def run_web_server():
    port = 10000
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Web server running on port {port}")
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
    # Web server PEHLE start karo — Render port scan karta hai
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
