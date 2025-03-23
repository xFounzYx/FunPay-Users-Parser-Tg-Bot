import re
import os
import tempfile
import shutil

def load_error_ids(error_filename):
    error_ids = set()
    try:
        with open(error_filename, "r", encoding="utf-8") as file:
            for line in file:
                match = re.search(r"https://funpay.com/users/(\d+)/", line)
                if match:
                    error_ids.add(int(match.group(1)))
    except FileNotFoundError:
        pass
    return error_ids

def clean_and_check_file(filename, error_filename):
    error_ids = load_error_ids(error_filename)


    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False) as temp_file:
        temp_filename = temp_file.name


        seen_lines = set()
        duplicates = set()


        seen_ids = set()


        min_id = float('inf')
        max_id = float('-inf')


        with open(filename, "r", encoding="utf-8") as file:
            for line in file:
                stripped_line = line.strip()
                if stripped_line in seen_lines:
                    duplicates.add(stripped_line)
                else:
                    seen_lines.add(stripped_line)
                    temp_file.write(stripped_line + "\n")


                    match = re.search(r"https://funpay.com/users/(\d+)/", stripped_line)
                    if match:
                        user_id = int(match.group(1))
                        seen_ids.add(user_id)
                        if user_id < min_id:
                            min_id = user_id
                        if user_id > max_id:
                            max_id = user_id


        if duplicates:
            print("🔴 Найдены дубликаты строк:")
            for dup in duplicates:
                print(dup)
        else:
            print("✅ Дубликатов не найдено.")


        temp_file.close()


        with open(temp_filename, "r", encoding="utf-8") as src, open(filename, "w", encoding="utf-8") as dst:
            shutil.copyfileobj(src, dst)


        os.remove(temp_filename)


    if min_id != float('inf') and max_id != float('-inf'):
        missing_ids = set()
        for user_id in range(min_id, max_id + 1):
            if user_id not in seen_ids and user_id not in error_ids:
                missing_ids.add(user_id)
    else:
        missing_ids = set()

    if missing_ids:
        with open(error_filename, "a", encoding="utf-8") as error_file:
            for missing_id in sorted(missing_ids):
                error_file.write(f"https://funpay.com/users/{missing_id}/ - error\n")

        print("\n⚠️ Новые пропущенные ID добавлены в errors_funpay.txt:")
        for missing_id in sorted(missing_ids):
            print(f"https://funpay.com/users/{missing_id}/ - missing")
    else:
        print("\n✅ Все ID идут по порядку, новых ошибок нет.")


clean_and_check_file("users_funpay.txt", "errors_funpay.txt")