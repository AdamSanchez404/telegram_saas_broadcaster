from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

def get_main_menu(is_broadcasting: bool = False, is_authorized: bool = False) -> ReplyKeyboardMarkup:
    """
    Главное меню бота с адаптивными кнопками.
    """
    auth_btn = "📱 Аккаунт подключен ✅" if is_authorized else "📱 Подключить аккаунт"
    broadcast_btn = "🛑 Остановить рассылку" if is_broadcasting else "🚀 Запустить рассылку"
    
    keyboard = [
        [KeyboardButton(text=auth_btn), KeyboardButton(text="✍️ Написать объявление с AI")],
        [KeyboardButton(text="⚙️ Настройки рассылки"), KeyboardButton(text=broadcast_btn)],
        [KeyboardButton(text="📊 Статистика и группы"), KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие в меню..."
    )

def get_interval_keyboard(current_interval: int = 30) -> InlineKeyboardMarkup:
    """
    Инлайн-клавиатура для выбора интервала отправки сообщений.
    """
    intervals = [
        (15, "15 минут"),
        (30, "30 минут"),
        (60, "1 час"),
        (120, "2 часа"),
        (240, "4 часа"),
    ]
    
    buttons = []
    row = []
    for minutes, label in intervals:
        check = "✓ " if minutes == current_interval else ""
        row.append(InlineKeyboardButton(
            text=f"{check}{label}",
            callback_data=f"set_interval:{minutes}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    buttons.append([InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_ad_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура после генерации AI-объявления:
    позволяет утвердить, сгенерировать заново или ввести вручную.
    """
    keyboard = [
        [InlineKeyboardButton(text="✅ Утвердить и сохранить", callback_data="ad:approve")],
        [InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="ad:regenerate")],
        [InlineKeyboardButton(text="✏️ Редактировать вручную", callback_data="ad:edit_manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="ad:cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка быстрой отмены текущего шага FSM."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отменить")]],
        resize_keyboard=True
    )
