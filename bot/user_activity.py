import os
import psycopg2
from datetime import datetime

# Создаем соединение с базой данных PostgreSQL
def create_connection():
    # Используем переменную окружения DATABASE_URL для подключения к PostgreSQL
    db_url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(db_url)
    return conn

# Создаем таблицу для пользователей
def create_users_table():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
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
        cursor.execute("INSERT INTO users (user_id, first_interaction) VALUES (%s, %s)", 
                       (user_id, datetime.now()))
        conn.commit()
    except psycopg2.IntegrityError:
        # Если пользователь уже существует, просто игнорируем
        conn.rollback()
    finally:
        cursor.close()  # Закрываем курсор
        if conn:
            conn.close()  # Закрываем соединение только если оно существует

# Получаем количество уникальных пользователей за период
def get_users_count(start_date, end_date):
    conn = create_connection()
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM users WHERE first_interaction BETWEEN %s AND %s"
    cursor.execute(query, (start_date, end_date))
    result = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return result