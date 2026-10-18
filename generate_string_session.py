import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH

async def main():
    print("=" * 60)
    print("   Генератор Telethon StringSession для облачных хостингов")
    print("=" * 60)
    print("Этот скрипт авторизует ваш Telegram-аккаунт и сгенерирует")
    print("строку сессии (StringSession) для использования в переменных")
    print("окружения STRING_SESSION на Render, Railway, Fly.io и т.д.\n")

    api_id = TELEGRAM_API_ID
    api_hash = TELEGRAM_API_HASH

    if not api_id or not api_hash:
        print("API_ID или API_HASH не найдены в .env файле.")
        api_id_input = input("Введите ваш API_ID (с https://my.telegram.org): ").strip()
        api_hash_input = input("Введите ваш API_HASH: ").strip()
        try:
            api_id = int(api_id_input)
            api_hash = api_hash_input
        except ValueError:
            print("❌ Ошибка: API_ID должен быть числом.")
            return

    phone = input("\nВведите номер телефона аккаунта (например, +79991234567): ").strip()
    if not phone:
        print("❌ Номер телефона не указан.")
        return

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    try:
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            code = input("Введите код подтверждения из Telegram: ").strip().replace(" ", "")
            try:
                await client.sign_in(phone, code)
            except Exception as e:
                # Если требуется двухфакторная аутентификация (2FA)
                if "password" in str(e).lower() or "SessionPasswordNeededError" in type(e).__name__:
                    password = input("Введите ваш облачный пароль (2FA): ").strip()
                    await client.sign_in(password=password)
                else:
                    raise e

        session_string = client.session.save()
        me = await client.get_me()

        print("\n" + "=" * 60)
        print("🎉 УСПЕШНО! Аккаунт авторизован:")
        print(f"👤 Имя: {me.first_name}")
        print(f"🆔 ID: {me.id}")
        print(f"📱 Номер: {me.phone}")
        print("=" * 60)
        print("\n🔑 Ваша строка сессии (STRING_SESSION):\n")
        print(session_string)
        print("\n" + "=" * 60)
        print("📋 ИНСТРУКЦИЯ ДЛЯ ОБЛАЧНОГО ХОСТИНГА:")
        print("1. Скопируйте строку выше.")
        print("2. В панели хостинга (Render / Railway / Koyeb / Heroku):")
        print("   Добавьте переменную окружения:")
        print("   Имя:  STRING_SESSION")
        print(f"   Значение: {session_string[:15]}... (полный ключ)")
        print("=" * 60)

        # Предлагаем сохранить в локальный .env
        save_env = input("\nСохранить эту сессию в локальный файл .env? (y/n, по умолчанию y): ").strip().lower()
        if save_env in ("", "y", "yes", "д", "да"):
            env_path = ".env"
            lines = []
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

            # Обновляем или добавляем STRING_SESSION
            updated = False
            new_lines = []
            for line in lines:
                if line.startswith("STRING_SESSION="):
                    new_lines.append(f"STRING_SESSION={session_string}\n")
                    updated = True
                else:
                    new_lines.append(line)

            if not updated:
                if new_lines and not new_lines[-1].endswith("\n"):
                    new_lines.append("\n")
                new_lines.append(f"STRING_SESSION={session_string}\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            print("✅ STRING_SESSION успешно записана в .env файл!")

    except Exception as e:
        print(f"\n❌ Произошла ошибка при авторизации: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОперация отменена пользователем.")
