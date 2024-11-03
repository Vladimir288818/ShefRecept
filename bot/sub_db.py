import os 
import sqlite3
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class SubscriptionDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._create_tables()

    def _create_tables(self):
        """Создание таблиц в базе данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        user_id INTEGER PRIMARY KEY,
                        level TEXT DEFAULT 'free',
                        trial_recipes_left INTEGER DEFAULT 5,
                        subscription_end_date TIMESTAMP,
                        last_updated TIMESTAMP
                    )
                """)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Ошибка при создании таблиц: {e}")

    def initialize_user(self, user_id: int) -> bool:
        """Инициализация нового пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO subscriptions (
                        user_id, level, trial_recipes_left, last_updated
                    ) VALUES (?, 'free', 5, ?)
                """, (user_id, datetime.now()))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при инициализации пользователя: {e}")
            return False

    def get_user_subscription(self, user_id: int) -> dict:
        """Получение информации о подписке пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT level, trial_recipes_left, subscription_end_date, last_updated
                    FROM subscriptions WHERE user_id = ?
                """, (user_id,))
                row = cursor.fetchone()
                
                if row:
                    return {
                        "level": row[0],
                        "trial_recipes_left": row[1],
                        "subscription_end_date": row[2],
                        "last_updated": row[3]
                    }
                return None
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении информации о подписке: {e}")
            return None

    def update_subscription(self, user_id: int, level: str, duration: int) -> bool:
        """Обновление подписки пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                subscription_end_date = datetime.now() + timedelta(days=duration * 30)
                
                cursor.execute("""
                    INSERT INTO subscriptions (
                        user_id, level, subscription_end_date, last_updated
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        level=excluded.level,
                        subscription_end_date=excluded.subscription_end_date,
                        last_updated=excluded.last_updated
                """, (user_id, level, subscription_end_date, datetime.now()))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка при обновлении подписки: {e}")
            return False

    def reduce_trial_recipes(self, user_id: int) -> tuple[bool, int]:
        """Уменьшение количества пробных рецептов"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT trial_recipes_left, level
                    FROM subscriptions WHERE user_id = ?
                """, (user_id,))
                row = cursor.fetchone()
                
                if not row:
                    return False, 0
                    
                trial_recipes_left, level = row
                
                if level != "free":
                    return True, -1  # -1 означает безлимитный доступ
                    
                if trial_recipes_left > 0:
                    new_trial_recipes_left = trial_recipes_left - 1
                    cursor.execute("""
                        UPDATE subscriptions 
                        SET trial_recipes_left = ?, last_updated = ? 
                        WHERE user_id = ?
                    """, (new_trial_recipes_left, datetime.now(), user_id))
                    conn.commit()
                    return True, new_trial_recipes_left
                return False, 0
        except sqlite3.Error as e:
            logger.error(f"Ошибка при уменьшении пробных рецептов: {e}")
            return False, 0