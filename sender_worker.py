import asyncio
import logging
import os
import random
from typing import Optional
from aiogram import Bot
from telethon import TelegramClient, errors
from telethon.tl.types import Channel, Chat

from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    MIN_DELAY_BETWEEN_CHATS_SEC,
    MAX_DELAY_BETWEEN_CHATS_SEC
)
import database as db

logger = logging.getLogger("sender_worker")

async def send_user_broadcast(user: dict, bot: Optional[Bot] = None) -> None:
    """
    Выполняет один цикл рассылки для конкретного пользователя:
    1. Подгружает его персональный файл .session
    2. Подключается к Telegram через Telethon
    3. Получает список доступных групп/мегагрупп
    4. Отправляет сохраненное объявление с безопасными задержками
    5. Перехватывает FloodWait и ошибки доступа
    """
    user_id = user["telegram_id"]
    ad_text = user["ad_text"]
    session_path = user.get("session_path", "")

    if not session_path or not os.path.exists(session_path):
        logger.warning(f"Файл сессии для пользователя {user_id} не найден: {session_path}")
        await db.set_broadcasting_status(user_id, False)
        if bot:
            try:
                await bot.send_message(
                    user_id,
                    "⚠️ <b>Рассылка остановлена:</b> файл вашей сессии не найден. "
                    "Пожалуйста, повторно подключите аккаунт в меню."
                )
            except Exception:
                pass
        return

    # Telethon ожидает имя сессии без расширения '.session'
    session_base = session_path[:-8] if session_path.endswith(".session") else session_path
    client = TelegramClient(session_base, TELEGRAM_API_ID, TELEGRAM_API_HASH)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error(f"Пользователь {user_id} больше не авторизован в Telethon.")
            await db.update_user_auth(user_id, user.get("phone", ""), session_path, is_authorized=False)
            await db.set_broadcasting_status(user_id, False)
            if bot:
                try:
                    await bot.send_message(
                        user_id,
                        "❌ <b>Сессия аннулирована:</b> авторизация слетела или была сброшена в настройках Telegram. "
                        "Подключите аккаунт заново."
                    )
                except Exception:
                    pass
            await client.disconnect()
            return

        sent_count = 0
        skipped_count = 0

        # Перебираем диалоги аккаунта
        async for dialog in client.iter_dialogs():
            # Фильтруем только группы и супергруппы (не личные чаты и не каналы без права отправки)
            if not (dialog.is_group or (isinstance(dialog.entity, Channel) and not dialog.entity.broadcast)):
                continue

            chat_title = dialog.title or f"Chat_{dialog.id}"
            chat_id = dialog.id

            try:
                # Отправка сообщения в группу от имени личного аккаунта
                await client.send_message(dialog.entity, ad_text)
                sent_count += 1
                logger.info(f"[User {user_id}] Сообщение отправлено в '{chat_title}' (id={chat_id})")

                # Логируем успешную отправку
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "success")

                # Безопасная случайная задержка между группами (антиспам)
                delay = random.uniform(MIN_DELAY_BETWEEN_CHATS_SEC, MAX_DELAY_BETWEEN_CHATS_SEC)
                await asyncio.sleep(delay)

            except errors.FloodWaitError as e:
                logger.warning(f"[User {user_id}] Пойман FloodWait на {e.seconds} секунд в чате {chat_title}")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "flood_wait", f"Ждать {e.seconds} сек")
                
                # Если ожидание разумное (до 60 сек), спим и продолжаем, иначе останавливаем цикл
                if e.seconds <= 60:
                    await asyncio.sleep(e.seconds + 2)
                    continue
                else:
                    if bot:
                        try:
                            await bot.send_message(
                                user_id,
                                f"⏳ <b>Временный перерыв (FloodWait):</b> Telegram запросил паузу "
                                f"на <b>{e.seconds} секунд</b>. Текущий цикл рассылки прерван во избежание блокировки."
                            )
                        except Exception:
                            pass
                    break

            except (errors.ChatWriteForbiddenError, errors.UserBannedInChannelError):
                logger.warning(f"[User {user_id}] Нет прав на отправку сообщений в чат '{chat_title}'")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "forbidden", "Нет прав на запись")
                skipped_count += 1

            except errors.SlowModeWaitError as e:
                logger.warning(f"[User {user_id}] В чате '{chat_title}' включен медленный режим: {e.seconds} сек")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "slow_mode", f"Медленный режим {e.seconds}с")
                skipped_count += 1

            except errors.RPCError as e:
                logger.error(f"[User {user_id}] RPC ошибка в чате '{chat_title}': {e}")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "rpc_error", str(e))
                skipped_count += 1

            except Exception as e:
                logger.error(f"[User {user_id}] Неожиданная ошибка в чате '{chat_title}': {e}")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "error", str(e))
                skipped_count += 1

        # Обновляем статистику в базе данных
        await db.update_last_broadcast(user_id, new_sent_count=sent_count)

        # Отправляем уведомление пользователю с итогами цикла
        if bot and sent_count > 0:
            try:
                await bot.send_message(
                    user_id,
                    f"✅ <b>Цикл рассылки успешно завершен!</b>\n\n"
                    f"• Успешно отправлено: <b>{sent_count}</b> групп(ы)\n"
                    f"• Пропущено (нет прав/ограничения): <b>{skipped_count}</b>\n"
                    f"• Следующая отправка: через <b>{user.get('interval_minutes')} минут</b>."
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

    except Exception as e:
        logger.error(f"Критическая ошибка воркера для пользователя {user_id}: {e}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

async def start_broadcast_dispatcher(bot: Bot) -> None:
    """
    Главный бесконечный цикл фонового воркера (Dispatcher).
    Периодически опрашивает БД на наличие пользователей,
    у которых включена рассылка и наступило время следующей отправки.
    """
    logger.info("Фоновый диспетчер рассылки успешно запущен.")
    while True:
        try:
            # Получаем всех активных пользователей, подошедших по интервалу
            active_users = await db.get_active_broadcasters()
            
            if active_users:
                logger.info(f"Найдено {len(active_users)} пользователей для выполнения рассылки.")
                for user in active_users:
                    # Запускаем отправку для пользователя
                    await send_user_broadcast(user, bot)
                    # Небольшая пауза между пользователями
                    await asyncio.sleep(2)
        except asyncio.CancelledError:
            logger.info("Диспетчер рассылки остановлен.")
            break
        except Exception as e:
            logger.error(f"Непредвиденная ошибка в основном цикле воркера: {e}")

        # Проверяем базу каждые 20 секунд
        await asyncio.sleep(20)
