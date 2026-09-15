import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import BOT_TOKEN
import database as db
from auth_handlers import router as auth_router
from bot_handlers import router as bot_router
from keyboards import get_main_menu
from sender_worker import start_broadcast_dispatcher

# Настройка логирования в консоль
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

@dp.message(CommandStart())
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    Создает пользователя в базе данных и выводит главное интерактивное меню.
    """
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id)
    
    first_name = message.from_user.first_name or "Пользователь"
    is_auth = bool(user.get("is_authorized"))
    is_broadcasting = bool(user.get("is_broadcasting"))

    auth_status_text = "🟢 <b>Аккаунт подключен</b>" if is_auth else "🔴 <b>Аккаунт не подключен</b>"
    broadcast_status_text = "🚀 <b>Рассылка активна</b>" if is_broadcasting else "🛑 <b>Рассылка остановлена</b>"

    welcome_text = (
        f"👋 Здравствуйте, <b>{first_name}</b>!\n\n"
        "Добро пожаловать в <b>SaaS Telegram Broadcaster</b> — сервис автоматической "
        "рассылки логистических заявок по вашим группам и чатам.\n\n"
        f"• Статус сессии: {auth_status_text}\n"
        f"• Статус рассылки: {broadcast_status_text}\n"
        f"• Интервал: <b>{user.get('interval_minutes', 30)} минут</b>\n\n"
        "📌 <b>Быстрый старт:</b>\n"
        "1. Нажмите <b>📱 Подключить аккаунт</b> и авторизуйтесь.\n"
        "2. Нажмите <b>✍️ Написать объявление с AI</b> для генерации заявки через Gemini 2.5 Flash.\n"
        "3. Нажмите <b>🚀 Запустить рассылку</b> для старта фонового диспетчера."
    )

    await message.answer(
        welcome_text,
        reply_markup=get_main_menu(is_broadcasting=is_broadcasting, is_authorized=is_auth)
    )

async def main():
    """
    Главная точка входа в приложение:
    1. Проверяет наличие BOT_TOKEN
    2. Инициализирует таблицы базы данных SQLite
    3. Запускает фоновый воркер-диспетчер
    4. Запускает Long Polling бота
    """
    if not BOT_TOKEN:
        logger.error("КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не указан в файле .env!")
        print("\nПожалуйста, укажите токен вашего бота в файле .env (BOT_TOKEN=...)")
        return

    # Инициализация базы данных
    logger.info("Инициализация базы данных SQLite...")
    await db.init_db()

    # Инициализация бота для aiogram 3.7+
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Запуск фонового диспетчера рассылки в качестве асинхронного фонового таска
    worker_task = asyncio.create_task(start_broadcast_dispatcher(bot))

    logger.info("Запуск Telegram-бота (aiogram 3.x long polling)...")
    try:
        # Удаляем старые вебхуки, чтобы бот сразу начал отвечать
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        # Корректное завершение работы при остановке процесса
        logger.info("Остановка бота и фонового воркера...")
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Бот успешно остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Приложение завершило работу.")