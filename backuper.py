import os
import shutil
import time
import logging


logging.basicConfig(
    filename="backup.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Путь к оригинальному файлу
ORIGINAL_FILE = "users_funpay.txt"
# Директория для хранения бэкапов
BACKUP_DIR = "backups"
# Интервал создания бэкапов (в секундах)
BACKUP_INTERVAL = 300  # 5 минут

def create_backup():
    """ Создает резервную копию файла, если прошлый бэкап меньше оригинала """
    try:
        # Проверяем, существует ли оригинальный файл
        if not os.path.exists(ORIGINAL_FILE):
            logging.error(f"[⚠] Оригинальный файл {ORIGINAL_FILE} не найден.")
            return

        # Создаем директорию для бэкапов, если она не существует
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
            logging.info(f"[ℹ] Создана директория для бэкапов: {BACKUP_DIR}")

        # Получаем размер оригинального файла
        original_size = os.path.getsize(ORIGINAL_FILE)

        # Получаем список существующих бэкапов
        backups = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.startswith("users_funpay_backup_")],
            reverse=True,
        )

        # Если есть предыдущий бэкап, проверяем его размер
        if backups:
            last_backup = os.path.join(BACKUP_DIR, backups[0])
            last_backup_size = os.path.getsize(last_backup)

            # Если размер последнего бэкапа больше или равен оригиналу, пропускаем создание нового
            if last_backup_size >= original_size:
                logging.info(
                    f"[ℹ] Последний бэкап {last_backup} имеет размер {last_backup_size} байт, "
                    f"что больше или равно оригиналу ({original_size} байт). Бэкап не создан."
                )
                return

            # Удаляем предыдущий бэкап перед созданием нового
            os.remove(last_backup)
            logging.info(f"[ℹ] Удален предыдущий бэкап: {last_backup}")

        # Создаем новый бэкап
        backup_name = f"users_funpay_backup_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        shutil.copy2(ORIGINAL_FILE, backup_path)

        logging.info(
            f"[✔] Создан бэкап: {backup_path} (размер: {os.path.getsize(backup_path)} байт)"
        )

    except Exception as e:
        logging.error(f"[⚠] Ошибка при создании бэкапа: {e}")

def main():
    """ Основная функция """
    logging.info("[ℹ] Запуск скрипта для создания бэкапов.")
    while True:
        try:
            create_backup()
            time.sleep(BACKUP_INTERVAL)
        except KeyboardInterrupt:
            logging.info("\n[❌] Остановка скрипта (CTRL + C)")
            break
        except Exception as e:
            logging.error(f"[⚠] Ошибка в основном цикле: {e}")
            time.sleep(60) 

if __name__ == "__main__":
    main()
