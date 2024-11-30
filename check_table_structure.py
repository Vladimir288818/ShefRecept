import sqlite3

def check_table_structure(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(subscriptions)")
    columns = cursor.fetchall()
    conn.close()

    # Вывод структуры таблицы
    print("Структура таблицы 'subscriptions':")
    for column in columns:
        print(f"Column: {column[1]}, Type: {column[2]}, Default: {column[4]}")

if __name__ == "__main__":
    db_path = 'C:\Users\WIN10\Desktop\culinary_bot\subscriptions.db'  # Укажите путь к вашей базе данных
    check_table_structure(db_path)