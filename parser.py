import asyncio
import aiohttp
import random
import os
from checker import clean_and_check_file

START_ID = 1
MAX_CONCURRENT_REQUESTS = 40
OUTPUT_FILE = "users_funpay.txt"
ERROR_FILE = "errors_funpay.txt"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/118.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

PROXIES = [] #Вставьте сюда свои прокси (если есть)


processed_ids = set()
error_ids = set()

# Ограничение на размер кэша
MAX_CACHE_SIZE = 1000

# Ограничение на размер очереди
MAX_QUEUE_SIZE = 500

def load_processed_ids():
    if not os.path.exists(OUTPUT_FILE):
        return set()

    with open(OUTPUT_FILE, "r", encoding="utf-8-sig") as f:
        return {int(line.split("/")[-2]) for line in f if line.strip()}

def load_error_ids():
    if not os.path.exists(ERROR_FILE):
        return set()

    with open(ERROR_FILE, "r", encoding="utf-8-sig") as f:
        return {int(line.split("/")[-2]) for line in f if line.strip()}

def remove_error_id(user_id):
    if not os.path.exists(ERROR_FILE):
        return

    with open(ERROR_FILE, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    with open(ERROR_FILE, "w", encoding="utf-8-sig") as f:
        for line in lines:
            if line.strip() and str(user_id) not in line:
                f.write(line)

def clear_cache_if_needed():
    if len(processed_ids) > MAX_CACHE_SIZE:
        processed_ids.clear()
        print("[ℹ] Очищен кэш processed_ids.")
    if len(error_ids) > MAX_CACHE_SIZE:
        error_ids.clear()
        print("[ℹ] Очищен кэш error_ids.")

async def get_username(session, user_id):
    url = f"https://funpay.com/users/{user_id}/"
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    proxy = random.choice(PROXIES) if PROXIES else None

    try:
        async with session.get(url, headers=headers, proxy=proxy, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                username_start = html.find('<span class="mr4">')
                if username_start != -1:
                    username_end = html.find("</span>", username_start)
                    username = html[username_start + 18:username_end].strip()

                    print(f"[✔] Найден: {username} - {user_id}")

                    if user_id not in processed_ids:
                        with open(OUTPUT_FILE, "a", encoding="utf-8-sig") as f:
                            f.write(f"https://funpay.com/users/{user_id}/ - {username}\n")
                            f.flush()
                            os.fsync(f.fileno())

                        processed_ids.add(user_id)

                        if user_id in error_ids:
                            remove_error_id(user_id)
                            error_ids.discard(user_id)
                    return username
            elif response.status == 429:
                retry_after = int(response.headers.get("Retry-After", random.randint(10, 30)))
                print(f"[⏳] 429 Too Many Requests. Жду {retry_after} секунд...")
                await asyncio.sleep(retry_after)
                return await get_username(session, user_id)
            else:
                error_message = f"{url} - {response.status} {response.reason}"
                with open(ERROR_FILE, "a", encoding="utf-8-sig") as f:
                    f.write(f"{error_message}\n")
                    f.flush()
                    os.fsync(f.fileno())

                error_ids.add(user_id)
                return None
    except Exception as e:
        error_message = f"{url} - Ошибка: {str(e)}"
        with open(ERROR_FILE, "a", encoding="utf-8-sig") as f:
            f.write(f"{error_message}\n")
            f.flush()
            os.fsync(f.fileno())

        error_ids.add(user_id)
        print(f"[⚠] Ошибка при обработке ID {user_id} (прокси: {proxy}): {e}")
        return None

async def worker(session, queue):
    while True:
        user_id = await queue.get()
        if user_id is None:
            break
        await get_username(session, user_id)
        queue.task_done()

async def run_checker(queue):
    while True:
        await asyncio.sleep(180)
        print("\n[ℹ] Запуск чекера для проверки файлов...")
        clean_and_check_file(OUTPUT_FILE, ERROR_FILE)

        error_ids = load_error_ids()
        if error_ids:
            print(f"[ℹ] Найдено {len(error_ids)} ID с ошибками для повторной проверки.")
            for user_id in error_ids:
                if user_id not in processed_ids:
                    await queue.put(user_id)
                    print(f"[ℹ] Добавлен ID {user_id} с ошибкой для повторной проверки.")
                    remove_error_id(user_id)


        clear_cache_if_needed()

async def main():
    queue = asyncio.Queue()

    global processed_ids, error_ids
    processed_ids = load_processed_ids()
    error_ids = load_error_ids()
    print(f"[ℹ] Загружено {len(processed_ids)} обработанных ID.")
    print(f"[ℹ] Загружено {len(error_ids)} ID с ошибками для повторного парсинга.")

    for user_id in error_ids:
        if user_id not in processed_ids:
            await queue.put(user_id)

    user_id = START_ID
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = [asyncio.create_task(worker(session, queue)) for _ in range(MAX_CONCURRENT_REQUESTS)]
        checker_task = asyncio.create_task(run_checker(queue))

        try:
            while True:
                if queue.qsize() < MAX_QUEUE_SIZE:
                    await queue.put(user_id)
                    user_id += 1
                    while user_id in processed_ids:
                        user_id += 1
                else:
                    await asyncio.sleep(1) 
        except asyncio.CancelledError:
            print("\n[❌] Остановка скрипта (CTRL + C)")
        finally:
            for _ in workers:
                await queue.put(None)
            await asyncio.gather(*workers, return_exceptions=True)


            checker_task.cancel()
            try:
                await checker_task
            except asyncio.CancelledError:
                print("\n[ℹ] Чекер остановлен.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[❌] Скрипт остановлен пользователем.")
