import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from ai_helper import generate_logistics_ad
from keyboards import (
    get_main_menu,
    get_interval_keyboard,
    get_ad_confirmation_keyboard,
    get_cancel_keyboard
)

logger = logging.getLogger(__name__)
router = Router(name="bot_handlers_router")

class AdStates(StatesGroup):
    waiting_for_raw_text = State()
    waiting_for_manual_text = State()

@router.message(F.text == "✍️ Написать объявление с AI")
async def start_ad_creation(message: Message, state: FSMContext):
    """
    Запрос у пользователя сырого текста заявки для передачи в Gemini 2.5 Flash.
    """
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id)

    current_ad_info = ""
    if user.get("ad_text"):
        current_ad_info = (
            "📌 <b>Ваше текущее активное объявление:</b>\n"
            f"<i>{user.get('ad_text')[:180]}...</i>\n\n"
        )

    await state.set_state(AdStates.waiting_for_raw_text)
    await message.answer(
        f"{current_ad_info}"
        "✍️ <b>Генератор объявлений на базе Google Gemini 2.5 Flash</b>\n\n"
        "Отправьте мне сырой, черновой текст вашей заявки на перевозку или логистической услуги в свободной форме.\n\n"
        "<i>Пример:</i>\n"
        "<code>Ищу тент 20т из Москвы в Казань, погрузка завтра в 10:00, оплата 120 000 руб с НДС, звонить +79991234567 Иван</code>\n\n"
        "Нейросеть структурирует текст, расставит профессиональные эмодзи и хэштеги!",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AdStates.waiting_for_raw_text)
async def process_raw_text_for_ai(message: Message, state: FSMContext):
    """
    Обработка сырого текста через Gemini API и показ результата.
    """
    raw_text = message.text.strip()
    if len(raw_text) < 10:
        await message.answer("⚠️ Текст слишком короткий. Напишите подробнее маршрут, груз и условия.")
        return

    status_msg = await message.answer("✨ <i>Нейросеть Gemini 2.5 Flash обрабатывает вашу заявку...</i>")

    try:
        # Вызов функции генерации
        formatted_ad = await generate_logistics_ad(raw_text)
        await state.update_data(generated_ad=formatted_ad, raw_text=raw_text)

        await status_msg.delete()
        await message.answer(
            "📋 <b>Готовое объявление для рассылки:</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{formatted_ad}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Проверьте правильность и подтвердите сохранение:",
            reply_markup=get_ad_confirmation_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка генерации объявления: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при обращении к AI. Попробуйте еще раз.")

@router.callback_query(F.data == "ad:approve")
async def approve_ad(callback: CallbackQuery, state: FSMContext):
    """Сохранение утвержденного объявления в базу данных."""
    data = await state.get_data()
    generated_ad = data.get("generated_ad")
    raw_text = data.get("raw_text")

    if not generated_ad:
        await callback.answer("Ошибка: объявление не найдено.", show_alert=True)
        return

    user_id = callback.from_user.id
    await db.update_ad_text(user_id, generated_ad, raw_text)
    await state.clear()

    user = await db.get_or_create_user(user_id)
    await callback.message.edit_text(
        "✅ <b>Объявление успешно сохранено!</b>\n\n"
        "Теперь оно будет автоматически отправляться во все ваши группы при включении рассылки."
    )
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_menu(bool(user.get("is_broadcasting")), bool(user.get("is_authorized")))
    )

@router.callback_query(F.data == "ad:regenerate")
async def regenerate_ad(callback: CallbackQuery, state: FSMContext):
    """Повторная генерация объявления с немного измененным стилем."""
    data = await state.get_data()
    raw_text = data.get("raw_text")

    if not raw_text:
        await callback.answer("Сырой текст не найден. Напишите заново.", show_alert=True)
        return

    await callback.message.edit_text("🔄 <i>Перегенерирую объявление в Gemini...</i>")
    formatted_ad = await generate_logistics_ad(raw_text)
    await state.update_data(generated_ad=formatted_ad)

    await callback.message.edit_text(
        "📋 <b>Обновленный вариант объявления:</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{formatted_ad}\n"
        "━━━━━━━━━━━━━━━━━━━━",
        reply_markup=get_ad_confirmation_keyboard()
    )

@router.callback_query(F.data == "ad:edit_manual")
async def edit_ad_manual(callback: CallbackQuery, state: FSMContext):
    """Возможность отправить отредактированный текст вручную."""
    await state.set_state(AdStates.waiting_for_manual_text)
    await callback.message.edit_text(
        "✏️ Отправьте отредактированный текст объявления сообщением в чат:"
    )

@router.message(AdStates.waiting_for_manual_text)
async def process_manual_ad_text(message: Message, state: FSMContext):
    """Прием ручного текста объявления."""
    text = message.text.strip()
    user_id = message.from_user.id
    await db.update_ad_text(user_id, text, "Ручной ввод")
    await state.clear()

    user = await db.get_or_create_user(user_id)
    await message.answer(
        "✅ <b>Текст объявления сохранен вручную!</b>",
        reply_markup=get_main_menu(bool(user.get("is_broadcasting")), bool(user.get("is_authorized")))
    )

@router.callback_query(F.data == "ad:cancel")
async def cancel_ad(callback: CallbackQuery, state: FSMContext):
    """Отмена редактирования объявления."""
    await state.clear()
    await callback.message.edit_text("❌ Сохранение объявления отменено.")

@router.message(F.text == "⚙️ Настройки рассылки")
async def open_settings(message: Message):
    """Выбор интервала рассылки."""
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id)
    interval = user.get("interval_minutes", 30)

    await message.answer(
        f"⚙️ <b>Настройки интервала рассылки</b>\n\n"
        f"Текущий интервал отправки: <b>{interval} минут</b>.\n\n"
        "Выберите желаемую частоту повтора сообщений по чатам:",
        reply_markup=get_interval_keyboard(interval)
    )

@router.callback_query(F.data.startswith("set_interval:"))
async def handle_set_interval(callback: CallbackQuery):
    """Обработка выбора интервала."""
    minutes = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    await db.update_interval(user_id, minutes)

    await callback.message.edit_text(
        f"✅ <b>Интервал успешно обновлен!</b>\n\n"
        f"Теперь рассылка будет запускаться каждые <b>{minutes} минут</b>.",
        reply_markup=get_interval_keyboard(minutes)
    )

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """Возврат в меню из инлайн-клавиатуры."""
    await callback.message.delete()

@router.message(F.text.in_(["🚀 Запустить рассылку", "🛑 Остановить рассылку"]))
async def toggle_broadcasting_handler(message: Message):
    """
    Запуск или остановка фоновой рассылки.
    Проверяет наличие подключенного аккаунта и текста объявления.
    """
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id)
    is_currently_broadcasting = bool(user.get("is_broadcasting"))

    if not is_currently_broadcasting:
        # Пытаемся запустить
        if not user.get("is_authorized"):
            await message.answer(
                "❌ <b>Нельзя запустить рассылку!</b>\n\n"
                "Сначала подключите ваш личный Telegram-аккаунт через кнопку <b>📱 Подключить аккаунт</b>."
            )
            return

        if not user.get("ad_text"):
            await message.answer(
                "❌ <b>Текст объявления не задан!</b>\n\n"
                "Сначала создайте объявление через кнопку <b>✍️ Написать объявление с AI</b>."
            )
            return

        await db.set_broadcasting_status(user_id, True)
        await message.answer(
            "🚀 <b>Автоматическая рассылка успешно запущена!</b>\n\n"
            f"• Интервал отправки: <b>каждые {user.get('interval_minutes')} мин.</b>\n"
            "• Диспетчер рассылки отправляет сообщение по всем группам вашего аккаунта.\n"
            "• Между группами автоматически выдерживается безопасная пауза для защиты от FloodWait.",
            reply_markup=get_main_menu(is_broadcasting=True, is_authorized=True)
        )
    else:
        # Останавливаем рассылку
        await db.set_broadcasting_status(user_id, False)
        await message.answer(
            "🛑 <b>Рассылка остановлена!</b>\n\n"
            "Фоновый воркер больше не отправляет сообщения. Вы можете возобновить ее в любой момент.",
            reply_markup=get_main_menu(is_broadcasting=False, is_authorized=bool(user.get("is_authorized")))
        )

@router.message(F.text == "📊 Статистика и группы")
async def show_statistics(message: Message):
    """Отображение статистики рассылки и журнала отправки."""
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id)
    logs = await db.get_recent_logs(user_id, limit=5)

    status_str = "🟢 Активна" if user.get("is_broadcasting") else "🔴 Остановлена"
    auth_str = "Подключен ✅" if user.get("is_authorized") else "Не подключен ❌"

    logs_text = ""
    if logs:
        logs_text = "\n<b>Последние отправки:</b>\n"
        for log in logs:
            icon = "✅" if log['status'] == "success" else "⚠️"
            title = log['chat_title'] or f"Чат {log.get('chat_id')}"
            logs_text += f"{icon} {title}: {log['status']} ({log['created_at']})\n"
    else:
        logs_text = "\n<i>Журнал отправок пока пуст.</i>"

    await message.answer(
        f"📊 <b>Ваша статистика в SaaS-сервисе:</b>\n\n"
        f"• Статус авторизации: <b>{auth_str}</b>\n"
        f"• Статус рассылки: <b>{status_str}</b>\n"
        f"• Всего отправлено сообщений: <b>{user.get('total_sent', 0)}</b>\n"
        f"• Интервал: <b>{user.get('interval_minutes', 30)} мин.</b>\n"
        f"{logs_text}"
    )

@router.message(F.text == "ℹ️ Помощь")
async def show_help(message: Message):
    """Справка по работе с сервисом."""
    await message.answer(
        "ℹ️ <b>Инструкция по работе с SaaS-ботом:</b>\n\n"
        "1. <b>Подключите аккаунт</b>: отправьте ваш номер и код подтверждения от Telegram. "
        "Сессия безопасно сохранится в изолированном файле.\n"
        "2. <b>Создайте объявление</b>: напишите диспетчерскую заявку в свободной форме, "
        "а Gemini 2.5 Flash оформит ее с эмодзи и контактами.\n"
        "3. <b>Настройте тайминг</b>: задайте интервал (рекомендуется 30–60 минут).\n"
        "4. <b>Запустите рассылку</b>: бот будет сам отправлять сообщения по всем вашим рабочим чатам, "
        "соблюдая паузы между группами для предотвращения банов."
    )
