import aiosqlite
import time
from typing import Optional, Dict, Any, List
from config import DATABASE_PATH, DEFAULT_INTERVAL_MINUTES

async def init_db() -> None:
    """
    Инициализация таблиц базы данных SQLite.
    Создает таблицы users и logs, если они отсутствуют,
    и выполняет автоматические миграции колонок при необходимости.
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Таблица пользователей сервиса
        await db.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                phone TEXT,
                session_path TEXT,
                session_string TEXT,
                is_authorized INTEGER DEFAULT 0,
                ad_text TEXT,
                raw_ad_text TEXT,
                interval_minutes INTEGER DEFAULT {DEFAULT_INTERVAL_MINUTES},
                is_broadcasting INTEGER DEFAULT 0,
                last_broadcast_at INTEGER DEFAULT 0,
                total_sent INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Миграция: добавляем session_string в существующую таблицу users, если её еще нет
        try:
            await db.execute("ALTER TABLE users ADD COLUMN session_string TEXT")
        except Exception:
            # Колонка уже существует, ничего делать не нужно
            pass

        # Таблица логов рассылки по группам
        await db.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                chat_title TEXT,
                status TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        """)
        await db.commit()

async def get_or_create_user(telegram_id: int) -> Dict[str, Any]:
    """Получает пользователя по ID или создает новую запись."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = await cursor.fetchone()
        
        if not user:
            await db.execute(
                "INSERT INTO users (telegram_id, interval_minutes) VALUES (?, ?)",
                (telegram_id, DEFAULT_INTERVAL_MINUTES)
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user = await cursor.fetchone()
            
        return dict(user)

async def update_user_auth(
    telegram_id: int,
    phone: str,
    session_string: Optional[str] = None,
    session_path: Optional[str] = None,
    is_authorized: bool = True
) -> None:
    """
    Обновляет статус авторизации и Telethon StringSession (или путь к .session файлу).
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE users 
            SET phone = ?, 
                session_string = COALESCE(?, session_string),
                session_path = COALESCE(?, session_path),
                is_authorized = ? 
            WHERE telegram_id = ?
            """,
            (phone, session_string, session_path, 1 if is_authorized else 0, telegram_id)
        )
        await db.commit()

async def delete_user_auth(telegram_id: int) -> None:
    """Сбрасывает сессию и отключает рассылку."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE users 
            SET phone = NULL, session_string = NULL, session_path = NULL, is_authorized = 0, is_broadcasting = 0 
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        )
        await db.commit()

async def update_ad_text(telegram_id: int, ad_text: str, raw_ad_text: Optional[str] = None) -> None:
    """Сохраняет сгенерированный или отредактированный текст объявления."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET ad_text = ?, raw_ad_text = ? WHERE telegram_id = ?",
            (ad_text, raw_ad_text, telegram_id)
        )
        await db.commit()

async def update_interval(telegram_id: int, interval_minutes: int) -> None:
    """Устанавливает интервал повтора рассылки в минутах."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET interval_minutes = ? WHERE telegram_id = ?",
            (interval_minutes, telegram_id)
        )
        await db.commit()

async def set_broadcasting_status(telegram_id: int, is_broadcasting: bool) -> None:
    """Включает или выключает статус рассылки для пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET is_broadcasting = ? WHERE telegram_id = ?",
            (1 if is_broadcasting else 0, telegram_id)
        )
        await db.commit()

async def get_active_broadcasters() -> List[Dict[str, Any]]:
    """
    Возвращает список пользователей, у которых:
    - подключена сессия (is_authorized = 1)
    - включена рассылка (is_broadcasting = 1)
    - задан текст объявления (ad_text IS NOT NULL и не пустой)
    - подошло время очередной отправки (now - last_broadcast_at >= interval_minutes * 60)
    """
    current_timestamp = int(time.time())
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT * FROM users
            WHERE is_authorized = 1 
              AND is_broadcasting = 1 
              AND ad_text IS NOT NULL 
              AND ad_text != ''
              AND (? - last_broadcast_at) >= (interval_minutes * 60)
        """
        cursor = await db.execute(query, (current_timestamp,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def update_last_broadcast(telegram_id: int, new_sent_count: int = 0) -> None:
    """Обновляет отметку времени последней рассылки и увеличивает счетчик отправленных сообщений."""
    current_timestamp = int(time.time())
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE users 
            SET last_broadcast_at = ?, total_sent = total_sent + ? 
            WHERE telegram_id = ?
            """,
            (current_timestamp, new_sent_count, telegram_id)
        )
        await db.commit()

async def log_broadcast_attempt(
    user_id: int,
    chat_id: int,
    chat_title: str,
    status: str,
    error_message: Optional[str] = None
) -> None:
    """Записывает событие отправки в лог для аудита и отладки."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO broadcast_logs (user_id, chat_id, chat_title, status, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, chat_title, status, error_message)
        )
        await db.commit()

async def get_recent_logs(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Возвращает последние записи из журнала рассылки конкретного пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT chat_title, status, error_message, created_at 
            FROM broadcast_logs 
            WHERE user_id = ? 
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]