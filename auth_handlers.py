import logging
import os
from typing import Dict
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from telethon import TelegramClient, errors

from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSIONS_DIR
import database as db
from keyboards import get_main_menu, get_cancel_keyboard

logger = logging.getLogger(__name__)
router = Router(name="auth_router")

# Хранилище временных клиентов Telethon во время авторизации
# Ключ - telegram_id пользователя
active_auth_clients: Dict[int, TelegramClient] = {}

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()

@router.message(F.text.in_(["📱 Подключить аккаунт", "📱 Аккаунт подключен ✅"]))
async def start_auth_process(message: Message, state: FSMContext):
    """
    Начало процедуры привязки личного Telegram-аккаунта через Telethon.
    """
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id)

    if user.get("is_authorized"):
        session_file = os.path.exists(user.get("session_path", ""))
        await message.answer(
            f"📱 <b>Ваш аккаунт уже подключен!</b>\n\n"
            f"• Номер телефона: <code>{user.get('phone')}</code>\n"
            f"• Статус файла сессии: {'✅ На диске' if session_file else '⚠️ Файл не найден'}\n\n"
            "Если вы хотите перепривязать аккаунт или подключить другой номер, "
            "нажмите кнопку ниже для сброса текущей сессии.",
            reply_markup=get_main_menu(bool(user.get("is_broadcasting")), True)
        )
        return

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        await message.answer(
            "⚠️ <b>Внимание:</b> На сервере не заданы <code>TELEGRAM_API_ID</code> "
            "и <code>TELEGRAM_API_HASH</code> в файле .env!\n\n"
            "Получите их бесплатно на официальном сайте https://my.telegram.org и укажите в настройках бота."
        )
        return

    await state.set_state(AuthStates.waiting_for_phone)
    await message.answer(
        "📱 <b>Подключение Telegram-аккаунта для рассылки</b>\n\n"
        "Рассылка будет происходить от имени вашего личного аккаунта "
        "по тем группам и чатам, в которых вы состоите.\n\n"
        "Отправьте ваш номер телефона в международном формате, например:\n"
        "<code>+79991234567</code> или <code>+380991234567</code>",
        reply_markup=get_cancel_keyboard()
    )

@router.message(F.text == "❌ Отменить")
async def cancel_auth(message: Message, state: FSMContext):
    """Отмена текущего процесса ввода данных."""
    user_id = message.from_user.id
    if user_id in active_auth_clients:
        try:
            await active_auth_clients[user_id].disconnect()
        except Exception:
            pass
        del active_auth_clients[user_id]

    await state.clear()
    user = await db.get_or_create_user(user_id)
    await message.answer(
        "Действие отменено.",
        reply_markup=get_main_menu(bool(user.get("is_broadcasting")), bool(user.get("is_authorized")))
    )

@router.message(AuthStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """
    Получение номера телефона и отправка кода авторизации через Telethon.
    """
    user_id = message.from_user.id
    phone = message.text.strip().replace(" ", "").replace("-", "")

    if not (phone.startswith("+") and phone[1:].isdigit() and len(phone) >= 10):
        await message.answer(
            "❌ Неверный формат номера! Номер должен начинаться с знака <b>+</b> "
            "и содержать только цифры. Попробуйте еще раз:\n"
            "Пример: <code>+79991234567</code>"
        )
        return

    # Путь к персональной сессии пользователя
    session_path = str(SESSIONS_DIR / f"user_{user_id}")
    
    # Создаем экземпляр клиента Telethon
    client = TelegramClient(session_path, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    try:
        await client.connect()
        # Запрашиваем одноразовый код у Telegram
        send_code_result = await client.send_code_request(phone)
        
        # Сохраняем клиента и хэш кода
        active_auth_clients[user_id] = client
        await state.update_data(
            phone=phone,
            phone_code_hash=send_code_result.phone_code_hash,
            session_path=session_path + ".session"
        )
        await state.set_state(AuthStates.waiting_for_code)

        await message.answer(
            f"📩 <b>Код отправлен на номер {phone}!</b>\n\n"
            "Проверьте системные уведомления в приложении Telegram (или SMS) "
            "и введите полученный код сюда.\n\n"
            "💡 <i>Совет: Чтобы Telegram не блокировал код, можно вводить его с пробелом "
            "между цифрами, например: <code>1 2 3 4 5</code>.</i>",
            reply_markup=get_cancel_keyboard()
        )
    except errors.PhoneNumberInvalidError:
        await client.disconnect()
        await message.answer("❌ Telegram сообщает: такой номер телефона не существует.")
    except errors.FloodWaitError as e:
        await client.disconnect()
        await message.answer(
            f"⏳ <b>FloodWait от Telegram:</b> Слишком много попыток запроса кода. "
            f"Пожалуйста, подождите {e.seconds} секунд перед повторной попыткой."
        )
        await state.clear()
    except Exception as e:
        await client.disconnect()
        logger.error(f"Ошибка при запросе кода для {phone}: {e}")
        await message.answer(f"❌ Ошибка отправки запроса в Telegram: {e}")
        await state.clear()

@router.message(AuthStates.waiting_for_code)
async def process_code(message: Message, state: FSMContext):
    """
    Прием кода от Telegram и завершение входа (или запрос пароля 2FA).
    """
    user_id = message.from_user.id
    code = message.text.strip().replace(" ", "").replace("-", "")

    client = active_auth_clients.get(user_id)
    if not client:
        await message.answer("❌ Время сессии авторизации истекло. Пожалуйста, начните заново.")
        await state.clear()
        return

    data = await state.get_data()
    phone = data.get("phone")
    phone_code_hash = data.get("phone_code_hash")
    session_path = data.get("session_path")

    try:
        # Авторизуемся по коду
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        
        # Получаем данные профиля для подтверждения
        me = await client.get_me()
        user_name = me.first_name or "Пользователь"
        
        # Отключаем клиент, сессия сохранена в .session файл
        await client.disconnect()
        del active_auth_clients[user_id]

        # Записываем статус в базу данных
        await db.update_user_auth(user_id, phone, session_path, is_authorized=True)
        await state.clear()

        await message.answer(
            f"🎉 <b>Аккаунт успешно подключен!</b>\n\n"
            f"👤 Имя: <b>{user_name}</b>\n"
            f"📱 Номер: <code>{phone}</code>\n"
            f"💾 Сессия сохранена в файл: <code>{session_path}</code>\n\n"
            "Теперь вы можете составить объявление с помощью AI и запустить автоматическую рассылку по группам!",
            reply_markup=get_main_menu(is_broadcasting=False, is_authorized=True)
        )
    except errors.SessionPasswordNeededError:
        # У пользователя включена двухфакторная аутентификация (Облачный пароль)
        await state.set_state(AuthStates.waiting_for_2fa)
        await message.answer(
            "🔐 <b>Требуется облачный пароль (2FA)!</b>\n\n"
            "На вашем аккаунте включена двухфакторная защита. "
            "Введите ваш облачный пароль от Telegram:",
            reply_markup=get_cancel_keyboard()
        )
    except (errors.PhoneCodeInvalidError, errors.PhoneCodeEmptyError):
        await message.answer("❌ Неверный код! Проверьте цифры и попробуйте еще раз.")
    except errors.PhoneCodeExpiredError:
        await client.disconnect()
        if user_id in active_auth_clients:
            del active_auth_clients[user_id]
        await state.clear()
        await message.answer("⌛️ Срок действия кода истек. Пожалуйста, начните заново.")
    except Exception as e:
        logger.error(f"Ошибка при вводе кода: {e}")
        await message.answer(f"❌ Ошибка входа: {e}")

@router.message(AuthStates.waiting_for_2fa)
async def process_2fa_password(message: Message, state: FSMContext):
    """
    Прием облачного пароля 2FA и завершение входа.
    """
    user_id = message.from_user.id
    password = message.text.strip()

    client = active_auth_clients.get(user_id)
    if not client:
        await message.answer("❌ Время сессии авторизации истекло. Пожалуйста, начните заново.")
        await state.clear()
        return

    data = await state.get_data()
    phone = data.get("phone")
    session_path = data.get("session_path")

    try:
        await client.sign_in(password=password)
        me = await client.get_me()
        user_name = me.first_name or "Пользователь"

        await client.disconnect()
        del active_auth_clients[user_id]

        await db.update_user_auth(user_id, phone, session_path, is_authorized=True)
        await state.clear()

        await message.answer(
            f"🎉 <b>Двухфакторная авторизация пройдена!</b>\n\n"
            f"👤 Имя: <b>{user_name}</b>\n"
            f"📱 Номер: <code>{phone}</code>\n\n"
            "Ваш аккаунт полностью готов к работе в фоновом воркере рассылки!",
            reply_markup=get_main_menu(is_broadcasting=False, is_authorized=True)
        )
    except errors.PasswordHashInvalidError:
        await message.answer("❌ Неверный облачный пароль! Попробуйте еще раз:")
    except Exception as e:
        logger.error(f"Ошибка 2FA: {e}")
        await message.answer(f"❌ Ошибка авторизации: {e}")
