import os
import logging
import sqlite3
import asyncio
from telegram import Update
from telegram.error import TimedOut
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен вашего бота
TOKEN = ""

SEARCH_MODE = "match"

# ID админа в Telegram
ADMIN_ID = 

# Имя файла базы данных
DATABASE_FILE = "authorized_keys.db"


def init_db():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS authorized_keys (
                key TEXT PRIMARY KEY,
                user_id INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        conn.commit()


        cursor.execute("INSERT OR IGNORE INTO authorized_keys (key, user_id) VALUES (?, ?)", ("admin", ADMIN_ID))
        conn.commit()


def add_key_to_db(key: str, user_id: int = None):
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO authorized_keys (key, user_id) VALUES (?, ?)", (key, user_id))
        conn.commit()


def delete_key_from_db(key: str):
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM authorized_keys WHERE key = ?", (key,))
        conn.commit()
        return cursor.rowcount > 0


def ban_user(user_id: int):
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (user_id,))
        conn.commit()


def unban_user(user_id: int):
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0


def is_user_banned(user_id: int) -> bool:
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM banned_users WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None


def is_key_activated(key: str) -> bool:
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM authorized_keys WHERE key = ?", (key,))
        result = cursor.fetchone()
        return result is not None and result[0] is not None


def activate_key(key: str, user_id: int):
    if is_user_banned(user_id):
        return False
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE authorized_keys SET user_id = ? WHERE key = ? AND user_id IS NULL", (user_id, key))
        conn.commit()
        return cursor.rowcount > 0


def is_authorized(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key FROM authorized_keys WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None


def load_keys_from_db():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, user_id FROM authorized_keys")
        return {row[0]: row[1] for row in cursor.fetchall()}


init_db()


async def send_file_with_retry(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, caption: str = "", retries=3):
    for attempt in range(retries):
        try:
            if os.path.exists(file_path):
                with open(file_path, "rb") as file:
                    await update.message.reply_document(document=file, caption=caption)
                logger.info(f"Файл {file_path} успешно отправлен.")
                break
            else:
                await update.message.reply_text(f"Файл {file_path} не найден")
                break
        except TimedOut as e:
            if attempt < retries - 1:
                logger.warning(f"Тайм-аут при отправке файла {file_path}. Попытка {attempt + 1} из {retries}.")
                await asyncio.sleep(2)  
            else:
                logger.error(f"Не удалось отправить файл {file_path} после {retries} попыток.")
                await update.message.reply_text("❌ Не удалось отправить файл из-за тайм-аута")


async def check_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if is_user_banned(user_id):
        await update.message.reply_text("❌ Вы заблокированы и не можете использовать команды")
        return True  
    return False  


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if user_id == ADMIN_ID:
        await update.message.reply_text("👋 Привет, админ! Вы авторизованы автоматически")
    elif is_authorized(user_id):
        await update.message.reply_text("👋 Привет! Вы уже авторизованы")
    else:
        await update.message.reply_text("👋 Привет! Для использования бота введите ключ активации \n💰 Купить ключ можно у @founzy")


async def handle_key_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if user_id == ADMIN_ID:
        await update.message.reply_text("🔑 Админ не нуждается в ключе для авторизации")
        return

    key = update.message.text.strip()

    if is_key_activated(key):
        await update.message.reply_text("❌ Этот ключ уже активирован другим пользователем")
        return

    if activate_key(key, user_id):
        logger.info(f"Пользователь {update.message.from_user.username} успешно активировал ключ: {key}")
        await update.message.reply_text("✅ Ключ успешно активирован! Теперь вы можете использовать бота")
    else:
        logger.warning(f"Пользователь {update.message.from_user.username} ввел неверный ключ: {key}")
        await update.message.reply_text("❌ Неверный ключ")


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде")
        return

    logger.info(f"Пользователь {update.message.from_user.username} запросил файл users_funpay.txt")
    file_path = "users_funpay.txt"
    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:  
            await update.message.reply_text("Файл слишком большой. Разделяю на части...")
            part_files = split_file(file_path)
            for part_file in part_files:
                await send_file_with_retry(update, context, part_file, f"Файл users_funpay.txt, часть {part_files.index(part_file) + 1}/{len(part_files)}")
                os.remove(part_file) 
        else:
            await send_file_with_retry(update, context, file_path, "Файл users_funpay.txt")
    else:
        await update.message.reply_text("Файл users_funpay.txt не найден")


async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде")
        return

    logger.info(f"Пользователь {update.message.from_user.username} запросил файл errors_funpay.txt")
    await send_file_with_retry(update, context, "errors_funpay.txt", "Файл errors_funpay.txt")


def get_user_text(count: int) -> str:
    last_digit = count % 10
    last_two_digits = count % 100

    if last_digit == 1 and last_two_digits != 11:
        return f"Найден {count} пользователь"
    elif 2 <= last_digit <= 4 and not (12 <= last_two_digits <= 14):
        return f"Найдено {count} пользователя"
    else:
        return f"Найдено {count} пользователей"


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде")
        return

    logger.info(f"Пользователь {update.message.from_user.username} начал поиск.")
    try:

        args = context.args
        if len(args) < 1:
            await update.message.reply_text("Используйте команду так: /find <ник>")
            return

        nickname = " ".join(args)

        logger.info(f"Пользователь {update.message.from_user.username} ищет ник: {nickname} (режим: {SEARCH_MODE})")
        await update.message.reply_text(f"🔎 Начал поиск '{nickname}'")
        

        if os.path.exists("users_funpay.txt"):
            with open("users_funpay.txt", "r", encoding="utf-8") as file:
                lines = file.readlines()
                found_lines = []

                for line in lines:
                    if " - " in line:
                        url, username = line.strip().split(" - ", 1)
                        if SEARCH_MODE == "strict" and username.lower() == nickname.lower():
                            found_lines.append(f"{username} - {url}\n")
                        elif SEARCH_MODE == "match" and nickname.lower() in username.lower():
                            found_lines.append(f"{username} - {url}\n")

            if found_lines:

                response = "\n".join(found_lines)


                user_count = len(found_lines)
                user_text = get_user_text(user_count)

                await update.message.reply_text(user_text)


                if len(response) > 4096:
                    await update.message.reply_text("Сообщение слишком длинное, отправляю файлом...")
                    with open("found_users.txt", "w", encoding="utf-8") as f:
                        f.write(response)
                    await send_file_with_retry(update, context, "found_users.txt")
                    os.remove("found_users.txt")
                else:
                    await update.message.reply_text(response)
            else:
                await update.message.reply_text(f"Ник '{nickname}' не найден")
        else:
            await update.message.reply_text("Файл users_funpay.txt не найден")
    except IndexError:
        await update.message.reply_text("Используйте команду так: /find <ник>")


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде")
        return

    if os.path.exists("users_funpay.txt"):
        await update.message.reply_text(f"👀 Проверяю базу данных")
        with open("users_funpay.txt", "r", encoding="utf-8") as file:
            lines = file.readlines()
            count = len(lines)
            await update.message.reply_text(f"Количество пользователей в базе данных: {count}")
    else:
        await update.message.reply_text("Файл users_funpay.txt не найден")


async def set_mode_strict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде")
        return

    global SEARCH_MODE
    SEARCH_MODE = "strict"
    await update.message.reply_text("Режим поиска изменен на 'strict' (строгий)")


async def set_mode_match_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этой команде")
        return

    global SEARCH_MODE
    SEARCH_MODE = "match"
    await update.message.reply_text("Режим поиска изменен на 'match' (по совпадению)")


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:  
        await update.message.reply_text("❌ У вас нет прав для добавления ключей")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Используйте команду так: /add <ключ>")
        return

    key = args[0]
    add_key_to_db(key)
    await update.message.reply_text(f"✅ Ключ {key} успешно добавлен и готов к активации")


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:  
        await update.message.reply_text("❌ У вас нет прав для удаления ключей")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Используйте команду так: /delete <ключ>")
        return

    key = args[0]
    if delete_key_from_db(key):
        await update.message.reply_text(f"✅ Ключ {key} успешно удален")
    else:
        await update.message.reply_text(f"❌ Ключ {key} не найден")


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if user_id != ADMIN_ID: 
        await update.message.reply_text("❌ У вас нет прав для блокировки пользователей")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Используйте команду так: /ban <user_id или @username>")
        return

    target = args[0].strip()

    try:
        if target.startswith("@"):
            username = target

            try:
                user = await context.bot.get_chat(username)
                banned_user_id = user.id
            except Exception as e:
                await update.message.reply_text(f"❌ Пользователь {target} не найден")
                return
        else:

            banned_user_id = int(target)


        ban_user(banned_user_id)
        await update.message.reply_text(f"✅ Пользователь {target} (ID: {banned_user_id}) заблокирован")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Укажите числовой ID или юзернейм (например, @username)")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для разблокировки пользователей")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Используйте команду так: /unban <user_id или @username>")
        return

    target = args[0].strip()

    try:
        if target.startswith("@"):
            username = target
            try:
                user = await context.bot.get_chat(username)
                unbanned_user_id = user.id
            except Exception as e:
                await update.message.reply_text(f"❌ Пользователь {target} не найден")
                return
        else:
            unbanned_user_id = int(target)


        if unban_user(unbanned_user_id):
            await update.message.reply_text(f"✅ Пользователь {target} (ID: {unbanned_user_id}) разблокирован")
        else:
            await update.message.reply_text(f"❌ Пользователь {target} (ID: {unbanned_user_id}) не был заблокирован")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Укажите числовой ID или юзернейм (например, @username)")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update, context):
        return

    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для просмотра ключей")
        return

    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, user_id FROM authorized_keys")
        keys = cursor.fetchall()

        if not keys:
            await update.message.reply_text("❌ В базе данных нет ключей")
            return

        response = "Активные ключи и пользователи:\n\n"
        for key, user_id in keys:
            if user_id is not None:
                try:
                    user = await context.bot.get_chat(user_id)
                    username = f"@{user.username}" if user.username else "нет юзернейма"
                    response += f"{key} - {username} (ID: {user_id})\n\n"
                except Exception as e:
                    response += f"{key} - пользователь не найден (ID: {user_id})\n\n"
            else:
                response += f"{key} - не активирован\n\n"

        await update.message.reply_text(response)


def split_file(file_path, chunk_size=20 * 1024 * 1024):  # 20 МБ
    part_files = []
    part_num = 1
    current_size = 0
    current_lines = []

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            line_size = len(line.encode("utf-8"))
            if current_size + line_size > chunk_size and current_lines:
                part_file_path = f"{file_path}.part{part_num}"
                with open(part_file_path, "w", encoding="utf-8") as part_file:
                    part_file.writelines(current_lines)
                part_files.append(part_file_path)
                part_num += 1
                current_lines = []
                current_size = 0

            current_lines.append(line)
            current_size += line_size

        if current_lines:
            part_file_path = f"{file_path}.part{part_num}"
            with open(part_file_path, "w", encoding="utf-8") as part_file:
                part_file.writelines(current_lines)
            part_files.append(part_file_path)

    return part_files


def main():
    logger.info("Запуск бота...")
    application = ApplicationBuilder().token(TOKEN).read_timeout(30).write_timeout(30).build()


    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("errors", errors_command))
    application.add_handler(CommandHandler("find", find_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("set_mode_strict", set_mode_strict_command))
    application.add_handler(CommandHandler("set_mode_match", set_mode_match_command))
    application.add_handler(CommandHandler("add", add_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("keys", keys_command))


    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_key_message))

    logger.info("Бот запущен и ожидает команд...")
    application.run_polling()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[❌] Скрипт остановлен пользователем.")
