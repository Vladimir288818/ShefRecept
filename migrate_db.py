import os
import sqlite3
import psycopg2
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_data():
    logger.info("Запуск миграции данных из SQLite в PostgreSQL")

    # Подключение к SQLite
    sqlite_path = 'C:/Users/WIN10/Desktop/culinary_bot/users.db'
    logger.info(f"Подключение к SQLite: {sqlite_path}")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()

    # Подключение к PostgreSQL
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    try:
        logger.info("Подключение к PostgreSQL")
        pg_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        pg_cursor = pg_conn.cursor()

        # Проверка и создание таблицы users в PostgreSQL
        logger.info("Создание таблицы users, если она не существует")
        pg_cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE NOT NULL,
                first_interaction TIMESTAMP
            )
        """)
        pg_conn.commit()

        # Получаем данные из SQLite
        logger.info("Получение данных из таблицы users в SQLite")
        sqlite_cursor.execute("SELECT user_id, first_interaction FROM users")
        users = sqlite_cursor.fetchall()

        logger.info(f"Начало переноса {len(users)} записей в PostgreSQL")

        # Вставляем данные в PostgreSQL
        for user in users:
            pg_cursor.execute("""
                INSERT INTO users (user_id, first_interaction)
                VALUES (%s, %s)
            """, user)

        pg_conn.commit()
        logger.info(f"Успешно перенесено {len(users)} записей о пользователях")

    except Exception as e:
        logger.error(f"Ошибка при миграции: {e}")
        if 'pg_conn' in locals():
            pg_conn.rollback()

    finally:
        logger.info("Закрытие соединений")
        sqlite_cursor.close()
        sqlite_conn.close()
        if 'pg_cursor' in locals():
            pg_cursor.close()
        if 'pg_conn' in locals():
            pg_conn.close()

if __name__ == "__main__":
    migrate_data()