# sub_db.py
import os 
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from decimal import Decimal
from pathlib import Path
from .subscription_config import (
    SubscriptionTier, 
    PaymentStatus, 
    SUBSCRIPTION_DURATIONS,
    TRIAL_DURATION,
    TRIAL_USER_LIMIT
)

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Базовый класс для ошибок базы данных"""
    pass

class SubscriptionDB:
    def __init__(self, db_path: Union[str, Path]) -> None:
        """
        Инициализация базы данных подписок
        
        Args:
            db_path: Путь к файлу базы данных
        """
        self.db_path: Path = Path(db_path).resolve()
        self._create_db_file()
        self._create_tables()

    def _create_db_file(self) -> None:
        """Создание файла базы данных, если он не существует"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.db_path.exists():
                with sqlite3.connect(self.db_path) as conn:
                    logger.info(f"База данных создана: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Ошибка при создании базы данных: {e}")
            raise DatabaseError(f"Не удалось создать базу данных: {e}")

    def _create_tables(self) -> None:
        """Создание необходимых таблиц в базе данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        user_id INTEGER PRIMARY KEY,
                        subscription_level TEXT DEFAULT 'free',
                        registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        trial_end_date TIMESTAMP,
                        start_date TIMESTAMP,
                        end_date TIMESTAMP,
                        status TEXT DEFAULT 'free',
                        is_trial INTEGER DEFAULT 0,
                        special_price INTEGER DEFAULT 0,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        payment_id TEXT,
                        payment_status TEXT,
                        CONSTRAINT valid_subscription_level CHECK (
                            subscription_level IN ('free', 'trial', 'standard', 'premium')
                        ),
                        CONSTRAINT valid_status CHECK (
                            status IN ('free', 'trial', 'active', 'expired')
                        )
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS feature_usage (
                        user_id INTEGER,
                        feature_name TEXT,
                        usage_date DATE,
                        usage_count INTEGER DEFAULT 0,
                        PRIMARY KEY (user_id, feature_name, usage_date),
                        FOREIGN KEY (user_id) REFERENCES subscriptions(user_id)
                            ON DELETE CASCADE
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS payment_history (
                        payment_id TEXT PRIMARY KEY,
                        user_id INTEGER,
                        amount DECIMAL(10,2),
                        currency TEXT,
                        status TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES subscriptions(user_id)
                            ON DELETE CASCADE,
                        CONSTRAINT valid_payment_status CHECK (
                            status IN ('pending', 'succeeded', 'cancelled', 'failed')
                        )
                    )
                """)
                
                conn.commit()
                logger.info("Таблицы базы данных успешно созданы/обновлены")
                
        except sqlite3.Error as e:
            logger.error(f"Ошибка при создании таблиц: {e}")
            raise DatabaseError(f"Не удалось создать таблицы: {e}")
    def get_total_users_count(self) -> int:
        """
        Получение общего количества пользователей
        
        Returns:
            int: Общее количество пользователей
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(user_id) FROM subscriptions")
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Ошибка при подсчете пользователей: {e}")
            return 0
    def get_subscription_count(self, tier: str) -> int:
        """
        Получение количества пользователей с определенным типом подписки
    
        Args:
            tier: Тип подписки ('premium', 'standard', etc.)
        
        Returns:
            int: Количество пользователей
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(user_id) FROM subscriptions 
                    WHERE subscription_level = ? AND status = 'active'
                """, (tier,))
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Ошибка при подсчете подписок {tier}: {e}")
            return 0

    def get_trial_users_count(self) -> int:
        """
        Получение количества пользователей на пробном периоде
    
        Returns:
            int: Количество пользователей
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(user_id) FROM subscriptions 
                    WHERE is_trial = 1 AND status = 'trial'
                """)
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Ошибка при подсчете пробных пользователей: {e}")
            return 0

    def should_use_special_prices(self) -> bool:
        """
        Проверка, нужно ли использовать специальные цены
        
        Returns:
            bool: True если нужно использовать специальные цены
        """
        return self.get_total_users_count() < TRIAL_USER_LIMIT
    
    def initialize_user(self, user_id: int) -> Tuple[bool, bool]:
        """
        Инициализация нового пользователя
    
        Args:
            user_id: ID пользователя
    
        Returns:
            Tuple[bool, bool]: (успех операции, использовать ли специальные цены)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                use_special_prices = self.should_use_special_prices()
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                trial_end = (datetime.now() + TRIAL_DURATION).strftime('%Y-%m-%d %H:%M:%S')
            
                # Проверяем, существует ли пользователь
                cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE user_id = ?", (user_id,))
                if cursor.fetchone()[0] > 0:
                    return True, use_special_prices
            
                # Добавляем нового пользователя с пробным периодом
                cursor.execute("""
                    INSERT INTO subscriptions (
                        user_id, 
                        subscription_level, 
                        status,
                        registration_date,
                        trial_end_date,
                        is_trial,
                        special_price,
                        last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    'trial',
                    'trial',
                    now,
                    trial_end,
                    1,
                    1 if use_special_prices else 0,
                    now
                ))
            
                conn.commit()
                logger.info(
                    f"Пользователь {user_id} инициализирован "
                    f"(специальные цены: {'да' if use_special_prices else 'нет'})"
                )
                return True, use_special_prices
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка при инициализации пользователя {user_id}: {e}")
            raise DatabaseError(f"Не удалось инициализировать пользователя: {e}")

    def get_user_subscription(self, user_id: int) -> Optional[Dict[str, Union[str, datetime, bool, int]]]:
        """
        Получение информации о подписке пользователя
    
        Args:
            user_id: ID пользователя
    
        Returns:
            Optional[Dict[str, Union[str, datetime, bool, int]]]: Информация о подписке или None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT subscription_level, registration_date, trial_end_date, start_date, 
                           end_date, status, is_trial, special_price, last_updated,
                           payment_id, payment_status
                    FROM subscriptions WHERE user_id = ?
                """, (user_id,))
            
                row = cursor.fetchone()
            
                if row:
                    is_trial = bool(row[6])
                    trial_end_date = row[2]
                    registration_date = datetime.fromisoformat(row[1].replace(' ', 'T'))
                    now = datetime.now()
                
                    # Проверяем статус пробного периода
                    if is_trial and trial_end_date:
                        trial_end = datetime.fromisoformat(trial_end_date.replace(' ', 'T'))
                        days_left = (trial_end - now).days
                    
                        if days_left <= 0:
                            # Пробный период истек
                            self.end_trial_period(user_id)
                            return self.get_user_subscription(user_id)
                    
                        status_text = f"Пробный период (осталось {days_left} дней)"
                        subscription_level = "Пробный"
                    else:
                        status_text = str(row[5])
                        subscription_level = str(row[0])
                
                    return {
                        "subscription_level": subscription_level,
                        "registration_date": registration_date,
                        "trial_end_date": datetime.fromisoformat(trial_end_date.replace(' ', 'T')) if trial_end_date else None,
                        "start_date": datetime.fromisoformat(row[3].replace(' ', 'T')) if row[3] else None,
                        "end_date": datetime.fromisoformat(row[4].replace(' ', 'T')) if row[4] else None,
                        "status": status_text,
                        "is_trial": is_trial,
                        "special_price": bool(row[7]),
                        "last_updated": datetime.fromisoformat(row[8].replace(' ', 'T')),
                        "payment_id": str(row[9]) if row[9] else None,
                        "payment_status": str(row[10]) if row[10] else None,
                        "days_left": days_left if is_trial else None
                    }
            
                logger.warning(f"Пользователь {user_id} не найден")
                return None
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении информации о подписке: {e}")
            raise DatabaseError(f"Не удалось получить информацию о подписке: {e}")

    def update_subscription(self, user_id: int, tier: str, duration: int) -> bool:
        """
        Обновление подписки пользователя
        
        Args:
            user_id: ID пользователя
            tier: Уровень подписки (строка 'standard' или 'premium')
            duration: Длительность подписки в месяцах
            
        Returns:
            bool: Успех операции
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                subscription_end_date = (
                    datetime.now() + SUBSCRIPTION_DURATIONS[duration]
                ).strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute("""
                    UPDATE subscriptions
                    SET subscription_level = ?,
                        start_date = ?,
                        end_date = ?,
                        last_updated = ?,
                        status = 'active',
                        is_trial = 0
                    WHERE user_id = ?
                """, (tier, now, subscription_end_date, now, user_id))
                
                conn.commit()
                logger.info(f"Подписка пользователя {user_id} обновлена до уровня '{tier}' на {duration} месяцев")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Ошибка при обновлении подписки: {e}")
            raise DatabaseError(f"Не удалось обновить подписку: {e}")

    def end_trial_period(self, user_id: int) -> bool:
        """
        Завершение пробного периода пользователя
        
        Args:
            user_id: ID пользователя
        
        Returns:
            bool: Успех операции
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE subscriptions
                    SET is_trial = 0,
                        status = 'free',
                        subscription_level = 'free'
                    WHERE user_id = ? AND is_trial = 1
                """, (user_id,))
                
                conn.commit()
                logger.info(f"Пробный период для пользователя {user_id} завершен")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Ошибка при завершении пробного периода: {e}")
            raise DatabaseError(f"Не удалось завершить пробный период: {e}")
        
    def track_feature_usage(self, user_id: int, feature_name: str) -> bool:
        """
        Отслеживание использования функции
        
        Args:
            user_id: ID пользователя
            feature_name: Название функции
        
        Returns:
            bool: Успех операции
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                today = datetime.now().strftime('%Y-%m-%d')
                
                cursor.execute("""
                    INSERT INTO feature_usage (user_id, feature_name, usage_date, usage_count)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(user_id, feature_name, usage_date) 
                    DO UPDATE SET usage_count = usage_count + 1
                """, (user_id, feature_name, today))
                
                conn.commit()
                logger.info(f"Использование функции {feature_name} пользователем {user_id} отслежено")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Ошибка при отслеживании использования функции: {e}")
            raise DatabaseError(f"Не удалось отследить использование функции: {e}")

    def get_daily_feature_usage(self, user_id: int, feature_name: str) -> int:
        """
        Получение количества использований функции за текущий день
        
        Args:
            user_id: ID пользователя
            feature_name: Название функции
        
        Returns:
            int: Количество использований
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                today = datetime.now().strftime('%Y-%m-%d')
                
                cursor.execute("""
                    SELECT usage_count FROM feature_usage
                    WHERE user_id = ? AND feature_name = ? AND usage_date = ?
                """, (user_id, feature_name, today))
                
                result = cursor.fetchone()
                return result[0] if result else 0
                
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении статистики использования: {e}")
            raise DatabaseError(f"Не удалось получить статистику использования: {e}")

    def add_payment_record(self, user_id: int, payment_data: Dict[str, Union[str, float, int]]) -> bool:
        """
        Добавление записи о платеже
        Args:
            user_id: ID пользователя
            payment_data: Данные платежа (payment_id, amount, currency, status)
        
        Returns:
            bool: Успех операции
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute("""
                    INSERT INTO payment_history (
                        payment_id, user_id, amount, currency, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    payment_data['payment_id'],
                    user_id,
                    payment_data['amount'],
                    payment_data['currency'],
                    payment_data['status'],
                    now
                ))
                
                cursor.execute("""
                    UPDATE subscriptions 
                    SET payment_id = ?, 
                        payment_status = ?,
                        last_updated = ?
                    WHERE user_id = ?
                """, (payment_data['payment_id'], payment_data['status'], now, user_id))
                
                conn.commit()
                logger.info(f"Платеж {payment_data['payment_id']} для пользователя {user_id} добавлен")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Ошибка при добавлении платежа: {e}")
            raise DatabaseError(f"Не удалось добавить платеж: {e}")

    def update_payment_status(self, payment_id: str, status: PaymentStatus) -> bool:
        """
        Обновление статуса платежа
        
        Args:
            payment_id: ID платежа
            status: Новый статус
        
        Returns:
            bool: Успех операции
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute("""
                    UPDATE payment_history 
                    SET status = ?, 
                        updated_at = ?
                    WHERE payment_id = ?
                """, (status.value, now, payment_id))
                
                cursor.execute("""
                    UPDATE subscriptions 
                    SET payment_status = ?,
                        last_updated = ?
                    WHERE payment_id = ?
                """, (status.value, now, payment_id))
                
                conn.commit()
                logger.info(f"Статус платежа {payment_id} обновлен на {status.value}")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Ошибка при обновлении статуса платежа: {e}")
            raise DatabaseError(f"Не удалось обновить статус платежа: {e}")

    def get_payment_history(self, user_id: int) -> List[Dict[str, Union[str, float, datetime]]]:
        """
        Получение истории платежей пользователя
        
        Args:
            user_id: ID пользователя
        
        Returns:
            List[Dict[str, Union[str, float, datetime]]]: Список платежей
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT payment_id, amount, currency, status, created_at, updated_at
                    FROM payment_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                """, (user_id,))
                
                rows = cursor.fetchall()
                return [{
                    'payment_id': str(row[0]),
                    'amount': float(row[1]),
                    'currency': str(row[2]),
                    'status': str(row[3]),
                    'created_at': datetime.fromisoformat(row[4].replace(' ', 'T')),
                    'updated_at': datetime.fromisoformat(row[5].replace(' ', 'T'))
                } for row in rows]
                
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении истории платежей: {e}")
            raise DatabaseError(f"Не удалось получить историю платежей: {e}")