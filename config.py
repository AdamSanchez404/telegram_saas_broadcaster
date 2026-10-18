from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Конфигурация приложения на базе pydantic-settings.
    Автоматически считывает переменные из системного окружения (хостинга)
    или из локального файла .env.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Telegram Bot API токен (от @BotFather)
    BOT_TOKEN: str = Field(default="", description="Токен бота aiogram")

    # Telegram API credentials (с https://my.telegram.org)
    TELEGRAM_API_ID: int = Field(default=0, description="App API ID")
    TELEGRAM_API_HASH: str = Field(default="", description="App API Hash")

    # Telethon StringSession (для работы на облачных хостингах без постоянного диска)
    STRING_SESSION: str = Field(default="", description="Строка сессии Telethon")

    # Google Gemini API Key
    GEMINI_API_KEY: str = Field(default="", description="Ключ Gemini API")

    # Безопасные интервалы и задержки для предотвращения FloodWait и спам-банов
    MIN_DELAY_BETWEEN_CHATS_SEC: float = Field(default=25.0, description="Минимальная пауза между группами (сек)")
    MAX_DELAY_BETWEEN_CHATS_SEC: float = Field(default=60.0, description="Максимальная пауза между группами (сек)")
    DEFAULT_INTERVAL_MINUTES: int = Field(default=30, description="Интервал рассылки по умолчанию (мин)")

    # Пакетная пауза безопасности (антиспам)
    BATCH_SIZE: int = Field(default=10, description="Количество чатов перед дополнительной паузой")
    BATCH_PAUSE_SEC: float = Field(default=120.0, description="Длительность дополнительной паузы антиспама (сек)")

    # ID администратора (опционально)
    ADMIN_ID: Optional[int] = Field(default=None, description="Telegram ID администратора")

    # Порт для встроенного HTTP веб-сервера (Render.com Web Service)
    PORT: int = Field(default=10000, description="Порт встроенного веб-сервера для Render.com")

    # Базовые директории
    BASE_DIR: Path = Path(__file__).resolve().parent
    DATA_DIR: Path = Path(__file__).resolve().parent / "data"
    SESSIONS_DIR: Path = Path(__file__).resolve().parent / "sessions"
    DATABASE_PATH: Path = Path(__file__).resolve().parent / "data" / "saas_broadcaster.sqlite3"


# Создаем глобальный синглтон настроек
settings = Settings()

# Экспорт констант для обеспечения 100% обратной совместимости существующих импортов
BOT_TOKEN: str = settings.BOT_TOKEN
TELEGRAM_API_ID: int = settings.TELEGRAM_API_ID
TELEGRAM_API_HASH: str = settings.TELEGRAM_API_HASH
STRING_SESSION: str = settings.STRING_SESSION
GEMINI_API_KEY: str = settings.GEMINI_API_KEY

MIN_DELAY_BETWEEN_CHATS_SEC: float = settings.MIN_DELAY_BETWEEN_CHATS_SEC
MAX_DELAY_BETWEEN_CHATS_SEC: float = settings.MAX_DELAY_BETWEEN_CHATS_SEC
DEFAULT_INTERVAL_MINUTES: int = settings.DEFAULT_INTERVAL_MINUTES
BATCH_SIZE: int = settings.BATCH_SIZE
BATCH_PAUSE_SEC: float = settings.BATCH_PAUSE_SEC
ADMIN_ID: Optional[int] = settings.ADMIN_ID
PORT: int = settings.PORT

BASE_DIR: Path = settings.BASE_DIR
DATA_DIR: Path = settings.DATA_DIR
SESSIONS_DIR: Path = settings.SESSIONS_DIR
DATABASE_PATH: Path = settings.DATABASE_PATH

# Создаем директории при необходимости (для локального режима или кэша)
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
