import asyncio
import logging
import os
import random
from typing import Optional, List
from aiogram import Bot
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import Channel

from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    STRING_SESSION,
    MIN_DELAY_BETWEEN_CHATS_SEC,
    MAX_DELAY_BETWEEN_CHATS_SEC,
    BATCH_SIZE,
    BATCH_PAUSE_SEC
)
import database as db

logger = logging.getLogger("sender_worker")

async def sync_env_string_session(bot: Optional[Bot] = None) -> None:
    """
    Если STRING_SESSION задана в переменных окружения хостинга (.env или Dashboard),
    автоматически проверяет валидность авторизации и регистрирует/обновляет пользователя в БД.
    """
    if not STRING_SESSION:
        return

    logger.info("Проверка переменной окружения STRING_SESSION...")
    client = TelegramClient(StringSession(STRING_SESSION), TELEGRAM_API_ID, TELEGRAM_API_HASH)
    try:
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            phone = me.phone or ""
            name = me.first_name or "Пользователь"
            logger.info(f"STRING_SESSION валидна! Авторизован аккаунт: {name} (ID: {me.id}, Телефон: {phone})")
            
            # Регистрируем пользователя в SQLite
            await db.get_or_create_user(me.id)
            await db.update_user_auth(me.id, phone, session_string=STRING_SESSION, is_authorized=True)
        else:
            logger.warning("Переменная STRING_SESSION задана, но сессия не авторизована в Telegram (отозвана).")
    except Exception as e:
        logger.error(f"Не удалось проверить STRING_SESSION при старте: {e}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

def create_telethon_client(user: dict) -> Optional[TelegramClient]:
    """
    Создает экземпляр TelegramClient на основе StringSession
    или файла сессии (для обратной совместимости).
    """
    session_string = user.get("session_string") or STRING_SESSION
    session_path = user.get("session_path")

    # Приоритет 1: StringSession (не требует диска)
    if session_string and len(session_string.strip()) > 30:
        try:
            return TelegramClient(StringSession(session_string.strip()), TELEGRAM_API_ID, TELEGRAM_API_HASH)
        except Exception as e:
            logger.error(f"[User {user.get('telegram_id')}] Некорректный формат StringSession: {e}")
            return None

    # Приоритет 2: Локальный файл .session (обратная совместимость)
    if session_path and os.path.exists(session_path):
        try:
            session_base = session_path[:-8] if session_path.endswith(".session") else session_path
            return TelegramClient(session_base, TELEGRAM_API_ID, TELEGRAM_API_HASH)
        except Exception as e:
            logger.error(f"[User {user.get('telegram_id')}] Ошибка загрузки .session файла: {e}")
            return None

    return None

async def send_user_broadcast(user: dict, bot: Optional[Bot] = None) -> None:
    """
    Выполняет один цикл рассылки для конкретного пользователя:
    1. Инициализирует Telethon через StringSession в памяти
    2. Подключается и валидирует авторизацию
    3. Сканирует доступные группы/супергруппы с перехватом FloodWait
    4. Отправляет объявление с безопасными рандомизированными задержками и пакетными паузами
    5. Надежно обрабатывает PeerFloodError, FloodWaitError, RPCError
    """
    user_id = user["telegram_id"]
    ad_text = user["ad_text"]

    client = create_telethon_client(user)
    if not client:
        logger.warning(f"[User {user_id}] Сессия не найдена (нет session_string в БД и STRING_SESSION в env)")
        await db.set_broadcasting_status(user_id, False)
        if bot:
            try:
                await bot.send_message(
                    user_id,
                    "⚠️ <b>Рассылка остановлена:</b> не найдена строка авторизации StringSession.\n"
                    "Пожалуйста, подключите аккаунт в меню или добавьте <code>STRING_SESSION</code> в настройки хостинга."
                )
            except Exception:
                pass
        return

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error(f"[User {user_id}] Сессия отозвана или не авторизована.")
            await db.update_user_auth(user_id, user.get("phone", ""), is_authorized=False)
            await db.set_broadcasting_status(user_id, False)
            if bot:
                try:
                    await bot.send_message(
                        user_id,
                        "❌ <b>Сессия аннулирована:</b> авторизация слетела или была сброшена в Telegram.\n"
                        "Подключите аккаунт заново."
                    )
                except Exception:
                    pass
            return

        # Получаем целевые группы и супергруппы с безопасной обработкой ошибок
        target_dialogs: List = []
        try:
            async for dialog in client.iter_dialogs():
                if dialog.is_group or (isinstance(dialog.entity, Channel) and not dialog.entity.broadcast):
                    target_dialogs.append(dialog)
        except errors.FloodWaitError as e:
            logger.warning(f"[User {user_id}] FloodWait при получении списка групп: {e.seconds} сек")
            if bot:
                try:
                    await bot.send_message(
                        user_id,
                        f"⏳ <b>FloodWait от Telegram:</b> сканирование чатов временно ограничено на {e.seconds} сек."
                    )
                except Exception:
                    pass
            return
        except errors.RPCError as e:
            logger.error(f"[User {user_id}] RPC ошибка при чтении диалогов: {e}")
            return

        total_groups = len(target_dialogs)
        logger.info(f"[User {user_id}] Найдено доступных групп для рассылки: {total_groups}")

        if total_groups == 0:
            if bot:
                try:
                    await bot.send_message(
                        user_id,
                        "ℹ️ На вашем аккаунте не найдено доступных групп для рассылки. "
                        "Вступите в рабочие группы и перезапустите рассылку."
                    )
                except Exception:
                    pass
            return

        sent_count = 0
        skipped_count = 0

        for idx, dialog in enumerate(target_dialogs, start=1):
            chat_title = dialog.title or f"Chat_{dialog.id}"
            chat_id = dialog.id

            try:
                # Отправка рекламного сообщения в группу
                await client.send_message(dialog.entity, ad_text)
                sent_count += 1
                logger.info(f"[User {user_id}] [{idx}/{total_groups}] Сообщение отправлено в '{chat_title}' (id={chat_id})")

                # Логируем успешную отправку в БД
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "success")

                # Безопасные задержки (только если есть еще чаты впереди)
                if idx < total_groups:
                    # Пакетная пауза безопасности каждые BATCH_SIZE чатов
                    if sent_count > 0 and sent_count % BATCH_SIZE == 0:
                        batch_pause = BATCH_PAUSE_SEC + random.uniform(5.0, 25.0)
                        logger.info(
                            f"[User {user_id}] Отправлено пакетом {sent_count} сообщений. "
                            f"Антиспам-пауза: {batch_pause:.1f} сек..."
                        )
                        await asyncio.sleep(batch_pause)
                    else:
                        # Случайная безопасная задержка между отдельными чатами с микро-джиттером
                        base_delay = random.uniform(MIN_DELAY_BETWEEN_CHATS_SEC, MAX_DELAY_BETWEEN_CHATS_SEC)
                        jitter = random.uniform(0.5, 3.0)
                        total_delay = round(base_delay + jitter, 1)
                        logger.info(f"[User {user_id}] Безопасная пауза перед следующим чатом: {total_delay} сек...")
                        await asyncio.sleep(total_delay)

            except errors.FloodWaitError as e:
                logger.warning(f"[User {user_id}] Пойман FloodWait на {e.seconds} секунд в чате '{chat_title}'")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "flood_wait", f"Ждать {e.seconds} сек")
                
                # Если ожидание короткое (до 60 сек), спим с запасом и продолжаем
                if e.seconds <= 60:
                    wait_time = e.seconds + random.uniform(2.0, 5.0)
                    logger.info(f"[User {user_id}] Выжидаем FloodWait {wait_time:.1f} сек и продолжаем...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Длительный FloodWait — экстренно останавливаем текущий цикл во избежание блокировки
                    if bot:
                        try:
                            await bot.send_message(
                                user_id,
                                f"⏳ <b>Временный перерыв (FloodWait):</b> Telegram запросил паузу "
                                f"на <b>{e.seconds} секунд</b> (~{round(e.seconds / 60, 1)} мин).\n"
                                f"Текущий цикл рассылки прерван во избежание блокировки аккаунта. "
                                f"Следующая попытка состоится по расписанию."
                            )
                        except Exception:
                            pass
                    break

            except errors.PeerFloodError as e:
                # Критическая спам-блокировка Telegram (SpamBot)
                logger.critical(f"[User {user_id}] PeerFloodError в чате '{chat_title}': спам-фильтр Telegram активирован!")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "peer_flood", str(e))
                await db.set_broadcasting_status(user_id, False)
                if bot:
                    try:
                        await bot.send_message(
                            user_id,
                            "🚨 <b>Внимание: сработал спам-фильтр Telegram (PeerFloodError)!</b>\n\n"
                            "Telegram временно ограничил отправку сообщений в группы с вашего аккаунта.\n"
                            "Рассылка <b>автоматически остановлена</b> для предотвращения вечного бана аккаунта.\n\n"
                            "💡 <i>Проверьте статус и дату снятия ограничений в официальном боте:</i> @SpamBot"
                        )
                    except Exception:
                        pass
                break

            except (errors.AuthKeyUnregisteredError, errors.SessionRevokedError, errors.UserDeactivatedError, errors.UserDeactivatedBanError) as e:
                logger.critical(f"[User {user_id}] Сессия аннулирована или аккаунт забанен: {e}")
                await db.update_user_auth(user_id, user.get("phone", ""), is_authorized=False)
                await db.set_broadcasting_status(user_id, False)
                if bot:
                    try:
                        await bot.send_message(
                            user_id,
                            f"❌ <b>Сессия аннулирована:</b> {e.__class__.__name__}.\n"
                            "Рассылка остановлена. Пожалуйста, подключите аккаунт заново."
                        )
                    except Exception:
                        pass
                break

            except (errors.ChatWriteForbiddenError, errors.UserBannedInChannelError):
                logger.warning(f"[User {user_id}] Нет прав на отправку в '{chat_title}' (бан или режим 'только чтение')")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "forbidden", "Нет прав на запись")
                skipped_count += 1

            except (errors.ChatAdminRequiredError, errors.ChannelPrivateError):
                logger.warning(f"[User {user_id}] Чат '{chat_title}' стал приватным или требует прав администратора")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "admin_or_private", "Требуются права админа")
                skipped_count += 1

            except errors.SlowModeWaitError as e:
                logger.warning(f"[User {user_id}] В чате '{chat_title}' включен медленный режим ({e.seconds}с). Пропускаем.")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "slow_mode", f"Медленный режим {e.seconds}с")
                skipped_count += 1

            except errors.RPCError as e:
                logger.error(f"[User {user_id}] RPC ошибка в чате '{chat_title}': {e}")
                await db.log_broadcast_attempt(user_id, chat_id, chat_title, "rpc_error", str(e))
                skipped_count += 1
                await asyncio.sleep(random.uniform(2.0, 5.0))

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

    except asyncio.CancelledError:
        logger.info(f"[User {user_id}] Цикл рассылки был отменен.")
        raise
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

    # Если в переменных окружения хостинга передана STRING_SESSION, валидируем ее на старте
    if STRING_SESSION:
        try:
            await sync_env_string_session(bot)
        except Exception as e:
            logger.error(f"Ошибка предварительной синхронизации STRING_SESSION: {e}")

    while True:
        try:
            # Получаем всех активных пользователей, подошедших по интервалу
            active_users = await db.get_active_broadcasters()
            
            if active_users:
                logger.info(f"Найдено {len(active_users)} пользователей для выполнения рассылки.")
                for user in active_users:
                    # Запускаем отправку для пользователя
                    await send_user_broadcast(user, bot)
                    # Пауза между пользователями
                    await asyncio.sleep(random.uniform(2.0, 5.0))
        except asyncio.CancelledError:
            logger.info("Диспетчер рассылки остановлен.")
            break
        except Exception as e:
            logger.error(f"Непредвиденная ошибка в основном цикле воркера: {e}")

        # Проверяем базу каждые 20 секунд
        await asyncio.sleep(20)
