# 🚀 Telegram SaaS Auto-Broadcaster (aiogram 3 + Telethon + Gemini + StringSession)

Полнофункциональный асинхронный SaaS Telegram-сервис на Python для автоматической рассылки коммерческих сообщений и заявок по целевым группам и чатам от имени **личных аккаунтов пользователей**, полностью адаптированный для работы на **бесплатных облачных хостингах** (Render, Railway, Fly.io, Koyeb, Heroku) без постоянного диска.

---

## 🛠 Технологический стек

* **[aiogram 3.x](https://docs.aiogram.dev/)** — современный асинхронный фреймворк для взаимодействия с ботом, интерактивного меню и FSM.
* **[Telethon (StringSession)](https://docs.telethon.dev/)** — клиентский MTProto-движок с хранением авторизации в виде безопасной строки в памяти (`StringSession`), не требующий локальных `.session` файлов.
* **[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)** & **python-dotenv** — строгая типизированная загрузка переменных окружения из системы хостинга или `.env`.
* **[Google GenAI SDK](https://github.com/googleapis/python-genai)** — генерация и форматирование заявок с эмодзи и хэштегами.
* **[aiosqlite](https://github.com/omnilib/aiosqlite)** — надежная асинхронная база данных SQLite с автомиграциями.

---

## ☁️ Адаптация под бесплатные облачные хостинги

На бесплатных облачных платформах (Render, Railway, Koyeb и др.) файловая система **эфемерная** (сбрасывается при перезапуске или деплое). 
Этот проект полностью решает данную проблему:
1. **StringSession**: авторизация Telethon передается через строковую переменную `STRING_SESSION`. Никакие `.session` файлы не теряются.
2. **Безопасные задержки**: рандомизированные паузы (`asyncio.sleep` + микро-джиттер) между чатами + пакетные паузы безопасности.
3. **Защита от блокировок**: полный перехват `FloodWaitError`, `PeerFloodError` (SpamBot), `RPCError`, `SlowModeWaitError` и `ChatWriteForbiddenError`.

---

## 📂 Структура проекта

```
telegram_saas_broadcaster/
├── main.py                     # Точка входа, запуск бота и фонового диспетчера
├── config.py                   # Pydantic-settings конфигурация из переменных окружения
├── database.py                 # Асинхронные операции SQLite + поддержка StringSession
├── sender_worker.py            # Фоновый воркер с антиспам-паузами и обработкой RPC-ошибок
├── auth_handlers.py            # FSM-авторизация в Telethon со StringSession
├── bot_handlers.py             # Обработчики объявлений, настроек и статистики
├── keyboards.py                # Интерактивные меню и инлайн-клавиатуры
├── ai_helper.py                # Генератор объявлений
├── generate_string_session.py  # Утилита для генерации STRING_SESSION на локальном ПК
├── requirements.txt            # Зависимости Python
├── .env.example                # Шаблон конфигурации
└── README.md                   # Документация
```

---

## 🚀 Быстрый старт

### 1. Клонирование и установка зависимостей

```bash
git clone https://github.com/your-username/telegram-saas-broadcaster.git
cd telegram-saas-broadcaster

python -m venv venv
source venv/bin/activate  # Для Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Получение `STRING_SESSION`

Запустите локальный скрипт для быстрой авторизации вашего аккаунта Telegram:
```bash
python generate_string_session.py
```
Скрипт запросит код подтверждения из Telegram (и 2FA-пароль, если включен) и выдаст строку вида:
`1BVtsOIU...` — это ваш `STRING_SESSION`.

### 3. Настройка переменных окружения

Скопируйте пример:
```bash
cp .env.example .env
```
Заполните переменные:
* `BOT_TOKEN`: токен вашего бота от [@BotFather](https://t.me/BotFather)
* `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`: получите на [https://my.telegram.org](https://my.telegram.org)
* `STRING_SESSION`: полученная строка сессии
* `MIN_DELAY_BETWEEN_CHATS_SEC`: мин. пауза между группами (по умолчанию 25 сек)
* `MAX_DELAY_BETWEEN_CHATS_SEC`: макс. пауза между группами (по умолчанию 60 сек)
* `BATCH_SIZE`: каждые N чатов (по умолчанию 10)
* `BATCH_PAUSE_SEC`: длительность паузы безопасности (по умолчанию 120 сек)

### 4. Запуск проекта

```bash
python main.py
```

---

## 🌐 Развертывание на бесплатном облачном хостинге (Render, Railway, Koyeb)

1. Загрузите код в GitHub-репозиторий.
2. Создайте новый **Web Service** или **Background Worker** в панели хостинга (например, [Render.com](https://render.com)).
3. Укажите команду запуска:
   ```bash
   python main.py
   ```
4. В разделе **Environment Variables** добавьте:
   - `BOT_TOKEN`
   - `TELEGRAM_API_ID`
   - `TELEGRAM_API_HASH`
   - `STRING_SESSION`
5. Нажмите **Deploy**. Бот запустится без привязки к диску и сразу будет авторизован!

---

## 🛡 Безопасность и защита от спам-фильтров Telegram

| Ошибка / Событие | Поведение скрипта |
|---|---|
| **FloodWaitError (≤ 60 сек)** | Автоматическая пауза с джиттером и продолжение рассылки |
| **FloodWaitError (> 60 сек)** | Остановка текущего цикла во избежание жестких мер, уведомление владельца |
| **PeerFloodError (SpamBot)** | Немедленная остановка рассылки, перевод статуса в БД в `0`, алерт владельцу со ссылкой на @SpamBot |
| **ChatWriteForbiddenError** | Пропуск чата, логирование причины в БД |
| **SlowModeWaitError** | Пропуск чата с логированием для исключения зависания воркера |
| **AuthKeyUnregisteredError** | Автоматический сброс сессии и оповещение пользователя |
| **Рандомизированные задержки** | `random.uniform(min, max) + micro_jitter` между чатами |
| **Пакетная пауза** | Расширенная пауза антиспама каждые 10 чатов (120+ сек) |
