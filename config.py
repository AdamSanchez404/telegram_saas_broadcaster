import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# Telegram Bot API токен (от @BotFather)
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Telegram API credentials (с сайта https://my.telegram.org)
# Необходимы для создания клиентских сессий Telethon
TELEGRAM_API_ID: int = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")

# Google Gemini API Key для модели gemini-2.5-flash
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Базовые директории проекта
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
SESSIONS_DIR: Path = BASE_DIR / "sessions"

# Создаем необходимые директории, если они еще не существуют
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Путь к файлу базы данных SQLite
DATABASE_PATH: Path = DATA_DIR / "saas_broadcaster.sqlite3"

# Настройки рассылки по умолчанию
DEFAULT_INTERVAL_MINUTES: int = 30  # Интервал отправки по умолчанию
MIN_DELAY_BETWEEN_CHATS_SEC: int = 5   # Минимальная пауза между группами
MAX_DELAY_BETWEEN_CHATS_SEC: int = 15  # Максимальная пауза между группами
