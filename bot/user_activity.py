import sqlite3
from datetime import datetime

# Создаем соединение с базой данных
def create_connection():
    # Для удобства путь к базе данных можно передавать через переменную окружения
    db_path = 'C:/Users/WIN10/Desktop/culinary_bot/users.db'  # Укажите путь к базе данных
    conn = sqlite3.connect(db_path)
    return conn

# Создаем таблицу для пользователей
def create_users_table():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE,  -- Уникальный ID пользователя
            first_interaction TIMESTAMP  -- Время первого взаимодействия
        )
    ''')
    conn.commit()
    cursor.close()  # Закрываем курсор
    conn.close()  # Закрываем соединение

# Записываем взаимодействие пользователя
def log_user_interaction(user_id):
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (user_id, first_interaction) VALUES (?, ?)", 
                       (user_id, datetime.now()))
        conn.commit()
    except sqlite3.IntegrityError:
        # Если пользователь уже существует, просто игнорируем
        pass
    finally:
        cursor.close()  # Закрываем курсор
        if conn:
            conn.close()  # Закрываем соединение только если оно существует

# Получаем количество уникальных пользователей за период
def get_users_count(start_date, end_date):
    conn = create_connection()
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM users WHERE first_interaction BETWEEN ? AND ?"
    cursor.execute(query, (start_date, end_date))
    result = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return result