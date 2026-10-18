import asyncio
import logging
import os
import sys
from typing import Optional
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import BOT_TOKEN, STRING_SESSION, TELEGRAM_API_ID, TELEGRAM_API_HASH, PORT
import database as db
from auth_handlers import router as auth_router
from bot_handlers import router as bot_router
from keyboards import get_main_menu
from sender_worker import start_broadcast_dispatcher

# Настройка логирования в консоль
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

dp = Dispatcher(storage=MemoryStorage())

# Регистрация роутеров aiogram
dp.include_router(auth_router)
dp.include_router(bot_router)

# ============================================================
# Встроенный HTTP веб-сервер для Render.com (Health Check)
# ============================================================
async def handle_root(request: web.Request) -> web.Response:
    """Главный эндпоинт для проверки статуса сервиса на Render.com."""
    return web.Response(text="Bot is running! SaaS Telegram Broadcaster is active.")

async def handle_health(request: web.Request) -> web.Response:
    """Health check эндпоинт для мониторинга хостинга."""
    return web.Response(text="OK")

def create_web_app() -> web.Application:
    """Создание и конфигурация приложения aiohttp."""
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    return app

async def start_web_server(port: int = 10000) -> web.AppRunner:
    """
    Запускает неблокирующий асинхронный HTTP сервер на базе aiohttp.
    Слушает порт Render.com и отвечает на запросы проверки жизнеспособности (health check),
    не мешая работе aiogram long polling и Telethon.
    """
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info(f"[HTTP] Встроенный веб-сервер успешно запущен на http://0.0.0.0:{port} (Render.com Web Service готов)")
    return runner

# ============================================================
# Обработчики бота
# ============================================================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    Создает пользователя в базе данных и выводит главное интерактивное меню.
    """
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id)
    
    first_name = message.from_user.first_name or "Пользователь"
    
    # Проверяем авторизацию, включая переменную окружения STRING_SESSION
    is_auth = bool(user.get("is_authorized") or user.get("session_string") or STRING_SESSION)
    if is_auth and not user.get("is_authorized"):
        await db.update_user_auth(user_id, user.get("phone") or "", session_string=STRING_SESSION, is_authorized=True)
        user["is_authorized"] = 1

    is_broadcasting = bool(user.get("is_broadcasting"))

    auth_status_text = "🟢 <b>Аккаунт подключен (StringSession)</b>" if is_auth else "🔴 <b>Аккаунт не подключен</b>"
    broadcast_status_text = "🚀 <b>Рассылка активна</b>" if is_broadcasting else "🛑 <b>Рассылка остановлена</b>"

    welcome_text = (
        f"👋 Здравствуйте, <b>{first_name}</b>!\n\n"
        "Добро пожаловать в <b>SaaS Telegram Broadcaster</b> — сервис автоматической "
        "рассылки сообщений по вашим группам и чатам.\n\n"
        f"• Статус сессии: {auth_status_text}\n"
        f"• Статус рассылки: {broadcast_status_text}\n"
        f"• Интервал: <b>{user.get('interval_minutes', 30)} минут</b>\n\n"
        "📌 <b>Быстрый старт:</b>\n"
        "1. Нажмите <b>📱 Подключить аккаунт</b> и авторизуйтесь (сессия сохранится в памяти StringSession).\n"
        "2. Нажмите <b>✍️ Написать объявление с AI</b> для генерации текста.\n"
        "3. Нажмите <b>🚀 Запустить рассылку</b> для старта фонового диспетчера."
    )

    await message.answer(
        welcome_text,
        reply_markup=get_main_menu(is_broadcasting=is_broadcasting, is_authorized=is_auth)
    )

async def main():
    """
    Главная точка входа в приложение:
    1. Запускает неблокирующий HTTP веб-сервер на aiohttp для Render.com
    2. Проверяет наличие BOT_TOKEN
    3. Инициализирует таблицы базы данных SQLite
    4. Запускает фоновый воркер-диспетчер
    5. Запускает Long Polling бота
    """
    # Определяем порт для веб-сервера (из переменной PORT хостинга Render или config.py)
    server_port = int(os.getenv("PORT", str(PORT)))

    # 1. Запуск встроенного веб-сервера ДО бота и диспетчера
    web_runner: Optional[web.AppRunner] = None
    try:
        web_runner = await start_web_server(port=server_port)
    except Exception as e:
        logger.error(f"Не удалось запустить встроенный веб-сервер на порту {server_port}: {e}")

    if not BOT_TOKEN:
        logger.error("КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не указан в файле .env!")
        print("\nПожалуйста, укажите токен вашего бота в файле .env (BOT_TOKEN=...)")
        # Если нет токена бота, держим веб-сервер активным, чтобы контейнер не падал в циклический рестарт
        if web_runner:
            while True:
                await asyncio.sleep(3600)
        return

    # 2. Инициализация базы данных
    logger.info("Инициализация базы данных SQLite...")
    await db.init_db()

    if STRING_SESSION:
        logger.info("✅ STRING_SESSION обнаружена в переменных окружения (режим Cloud / Stateless).")
    else:
        logger.info("ℹ️ STRING_SESSION не задана в окружении. Авторизация доступна через бота или локальный скрипт.")

    # 3. Инициализация бота для aiogram 3.7+
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # 4. Запуск фонового диспетчера рассылки в качестве асинхронного фонового таска
    worker_task = asyncio.create_task(start_broadcast_dispatcher(bot))

    logger.info("Запуск Telegram-бота (aiogram 3.x long polling)...")
    try:
        # Удаляем старые вебхуки, чтобы бот сразу начал отвечать
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        # Корректное завершение работы при остановке процесса
        logger.info("Остановка бота, фонового воркера и веб-сервера...")
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

        # Корректная остановка HTTP сервера
        if web_runner:
            try:
                await web_runner.cleanup()
                logger.info("Встроенный HTTP веб-сервер успешно остановлен.")
            except Exception as e:
                logger.error(f"Ошибка при остановке веб-сервера: {e}")

        await bot.session.close()
        logger.info("Бот успешно остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Приложение завершило работу.")