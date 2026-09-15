# 🚀 Telegram SaaS Auto-Broadcaster (aiogram 3 + Telethon + Gemini 2.5 Flash)

Полнофункциональный SaaS Telegram-сервис на Python для автоматической рассылки коммерческих и логистических объявлений по целевым группам и чатам от имени **личных аккаунтов пользователей**.

---

## 🛠 Технологический стек

* **[aiogram 3.x](https://docs.aiogram.dev/)** — современный асинхронный фреймворк для взаимодействия с ботом, интерактивного меню и конечных автоматов (FSM).
* **[Telethon](https://docs.telethon.dev/)** — клиентский MTProto-движок для авторизации каждого пользователя по его номеру телефона и генерации персональных `.session` файлов.
* **[Google GenAI SDK (google-genai)](https://github.com/googleapis/python-genai)** — интеграция с новейшей языковой моделью **`gemini-2.5-flash`** для моментального превращения сырого текста заявки в структурированное объявление с логистическими эмодзи и контактами.
* **[aiosqlite](https://github.com/omnilib/aiosqlite)** — надежная асинхронная база данных SQLite для сохранения параметров пользователей, текстов объявлений, таймингов и журнала отправок.

---

## 📂 Архитектура проекта

```
telegram_saas_broadcaster/
├── main.py              # Точка входа, запуск бота и фонового диспетчера
├── config.py            # Загрузка .env, путей и настроек задержек
├── database.py          # Асинхронные операции с SQLite через aiosqlite
├── ai_helper.py         # Интеграция с Google Gemini 2.5 Flash
├── keyboards.py         # Главное меню, инлайн-кнопки интервалов и подтверждений
├── auth_handlers.py     # Пошаговая FSM-авторизация в Telethon (SMS-код, 2FA)
├── bot_handlers.py      # Обработчики AI-генерации, настроек и ручного ввода
├── sender_worker.py     # Фоновый воркер-диспетчер с перехватом FloodWait
├── sessions/            # Папка для изолированных .session файлов пользователей
├── data/                # Папка базы данных SQLite (saas_broadcaster.sqlite3)
├── requirements.txt     # Зависимости Python
├── .env.example         # Шаблон переменных окружения
└── README.md            # Документация проекта
```

---

## ⚙️ Установка и запуск

### 1. Клонирование и подготовка окружения

```bash
# Клонируйте репозиторий
git clone https://github.com/your-username/telegram-saas-broadcaster.git
cd telegram-saas-broadcaster

# Создайте и активируйте виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate

# Установите зависимости
pip install -r requirements.txt
```

### 2. Настройка переменных окружения (`.env`)

Скопируйте файл примера:
```bash
cp .env.example .env
```

Заполните переменные в `.env`:
* `BOT_TOKEN` — получите у [@BotFather](https://t.me/BotFather) в Telegram.
* `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` — получите бесплатно на официальном портале разработчиков [https://my.telegram.org](https://my.telegram.org) (раздел **API development tools**).
* `GEMINI_API_KEY` — получите бесплатно в [Google AI Studio](https://aistudio.google.com/app/apikey).

### 3. Запуск бота

```bash
python main.py
```

---

## 🛡 Защита от банов и Telegram FloodWait

1. **Изолированные сессии**: каждый пользователь авторизуется отдельно и рассылает сообщения **только по тем группам, в которых он уже состоит**.
2. **Рандомизированные задержки**: между отправками в разные группы выдерживается пауза от 5 до 15 секунд.
3. **Обработка `FloodWaitError`**: воркер автоматически улавливает ограничение, засыпает на требуемое количество секунд либо останавливает цикл и оповещает владельца аккаунта.
4. **Фильтрация чатов**: бот проверяет тип диалога и игнорирует приватные чаты и каналы только для чтения (`ChatWriteForbiddenError`).

---

## 🐳 Запуск через Docker (Опционально)

```bash
docker build -t telegram-saas-bot .
docker run -d --name tg_bot --env-file .env -v $(pwd)/sessions:/app/sessions -v $(pwd)/data:/app/data telegram-saas-bot
```
