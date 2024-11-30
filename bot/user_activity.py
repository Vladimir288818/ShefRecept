import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Базовый класс для ошибок базы данных"""
    pass

def get_database_path() -> Path:
    """
    Получение пути к базе данных пользователей
    
    Returns:
        Path: Путь к файлу базы данных
    """
    return Path("data/users.db").resolve()

def create_users_table() -> None:
    """Создание таблицы пользователей если она не существует"""
    try:
        # Создание директории для данных если её нет
        db_path = get_database_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_activity (
                    user_id INTEGER PRIMARY KEY,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    activity_count INTEGER DEFAULT 1
                )
            """)
            conn.commit()
            logger.info("Users table initialized successfully")
            
    except sqlite3.Error as e:
        logger.error(f"Failed to create users table: {e}")
        raise DatabaseError(f"Database initialization failed: {e}")

def log_user_interaction(user_id: int) -> None:
    """
    Логирование взаимодействия с пользователем
    
    Args:
        user_id (int): ID пользователя
    """
    try:
        db_path = get_database_path()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute("""
                INSERT INTO user_activity (user_id, last_activity, activity_count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_activity = ?,
                    activity_count = activity_count + 1
            """, (user_id, now, now))
            
            conn.commit()
            logger.info(f"User activity logged: {user_id}")
            
    except sqlite3.Error as e:
        logger.error(f"Failed to log user activity: {e}")

def get_users_count(start_date: datetime, end_date: datetime) -> int:
    """
    Получение количества активных пользователей за период
    
    Args:
        start_date (datetime): Начало периода
        end_date (datetime): Конец периода
    
    Returns:
        int: Количество активных пользователей
    """
    try:
        db_path = get_database_path()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) 
                FROM user_activity 
                WHERE last_activity BETWEEN ? AND ?
            """, (start_date.strftime('%Y-%m-%d %H:%M:%S'),
                 end_date.strftime('%Y-%m-%d %H:%M:%S')))
            
            return cursor.fetchone()[0]
            
    except sqlite3.Error as e:
        logger.error(f"Failed to get users count: {e}")
        return 0