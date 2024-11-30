#subscription_config.py
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import timedelta, datetime

class ConversationStates(Enum):
    CHOOSING_TIER = 5
    CHOOSING_DURATION = 6
    CHECKING_PAYMENT = 7

class FeatureType(Enum):
    FREE = "free"
    PREMIUM = "premium"
    STANDARD = "standard"

class SubscriptionTier(Enum):
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
    TRIAL = "trial"

    @classmethod
    def from_str(cls, value: str) -> Optional['SubscriptionTier']:
        """
        Получение типа подписки из строки
        
        Args:
            value: Строковое представление типа подписки
            
        Returns:
            SubscriptionTier или None
        """
        try:
            return cls(value.lower())
        except (ValueError, AttributeError):
            return None

class PaymentStatus(Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @classmethod
    def from_str(cls, value: str) -> Optional['PaymentStatus']:
        """
        Получение статуса платежа из строки
        
        Args:
            value: Строковое представление статуса
            
        Returns:
            PaymentStatus или None
        """
        try:
            return cls(value.lower())
        except (ValueError, AttributeError):
            return None

@dataclass
class SubscriptionFeature:
    name: str
    is_premium: bool
    is_standard: bool = False
    daily_limit: int = 0
    description: str = ""

    def to_dict(self) -> Dict:
        """Преобразование в словарь для сохранения в SQLite"""
        return {
            'name': self.name,
            'is_premium': int(self.is_premium),  # SQLite не поддерживает bool
            'is_standard': int(self.is_standard),
            'daily_limit': self.daily_limit,
            'description': self.description
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SubscriptionFeature':
        """Создание объекта из словаря из SQLite"""
        return cls(
            name=data['name'],
            is_premium=bool(data['is_premium']),
            is_standard=bool(data['is_standard']),
            daily_limit=data['daily_limit'],
            description=data['description']
        )

# Конфигурация функций для разных тарифов
PREMIUM_FEATURES: Dict[str, SubscriptionFeature] = {
    'ai_assistant': SubscriptionFeature(
        name='ai_assistant',
        is_premium=True,
        is_standard=False,
        description='Советы по выбору блюда или меню на различный период'
    ),
    'recipes_1952': SubscriptionFeature(
        name='recipes_1952',
        is_premium=True,
        is_standard=True,
        description='Доступ к рецептам из книги о вкусной и здоровой пище 1952 года'
    ),
    'ai_recipes': SubscriptionFeature(
        name='ai_recipes',
        is_premium=True,
        is_standard=False,
        description='Генерация рецептов с помощью искусственного интеллекта'
    ),
    'web_search': SubscriptionFeature(
        name='web_search',
        is_premium=True,
        is_standard=True,
        daily_limit=10,
        description='Поиск рецептов на сайте Edamam.com'
    ),
    'calculate_calories': SubscriptionFeature(
    name='calculate_calories',
    is_premium=True,
    is_standard=True,  # доступно в Standard и Premium
    description='Расчет калорийности блюд'
    )
}

# Лимиты для бесплатных пользователей
FREE_LIMITS: Dict[str, int] = {
    feature.name: feature.daily_limit 
    for feature in PREMIUM_FEATURES.values() 
    if not feature.is_premium
}

# Длительности подписок
SUBSCRIPTION_DURATIONS = {
    1: timedelta(days=30),    # 1 месяц
    3: timedelta(days=90),    # 3 месяца
    12: timedelta(days=365)   # 12 месяцев
}

def calculate_expiration_date(duration_months: int, start_date: Optional[datetime] = None) -> datetime:
    """
    Расчет даты окончания подписки
    
    Args:
        duration_months: Длительность подписки в месяцах
        start_date: Дата начала подписки (если None, используется текущая дата)
        
    Returns:
        datetime: Дата окончания подписки
    """
    if start_date is None:
        start_date = datetime.now()
    duration = SUBSCRIPTION_DURATIONS.get(duration_months)
    if duration:
        return start_date + duration
    raise ValueError(f"Invalid subscription duration: {duration_months}")

# Пробный период
TRIAL_DURATION = timedelta(days=14)
TRIAL_USER_LIMIT = 500

# Цены подписок
SUBSCRIPTION_PRICES_V1 = {
    SubscriptionTier.STANDARD.value: {
        1: 99,    # 1 месяц
        3: 275,   # 3 месяца
        12: 850   # 12 месяцев
    },
    SubscriptionTier.PREMIUM.value: {
        1: 149,    # 1 месяц
        3: 379,   # 3 месяца
        12: 1590   # 12 месяцев
    }
}

SUBSCRIPTION_PRICES_V2 = {
    SubscriptionTier.STANDARD.value: {
        1: 180,    # 1 месяц
        3: 375,   # 3 месяца
        12: 1450   # 12 месяцев
    },
    SubscriptionTier.PREMIUM.value: {
        1: 250,   # 1 месяц
        3: 575,   # 3 месяца
        12: 2250  # 12 месяцев
    }
}

def get_subscription_price(tier: SubscriptionTier, duration: int, user_count: int) -> int:
    """
    Получение цены подписки с учетом количества пользователей
    
    Args:
        tier: Тип подписки
        duration: Длительность подписки в месяцах
        user_count: Текущее количество пользователей
        
    Returns:
        int: Цена подписки
    """
    prices = SUBSCRIPTION_PRICES_V1 if user_count <= TRIAL_USER_LIMIT else SUBSCRIPTION_PRICES_V2
    return prices[tier.value][duration]

# Описания подписок
SUBSCRIPTION_DESCRIPTIONS = {
    SubscriptionTier.FREE.value: "Базовый доступ с ограничениями",
    SubscriptionTier.TRIAL.value: "Пробный период на 14 дней со всеми функциями",
    SubscriptionTier.STANDARD.value: (
        "✓ Поиск рецептов на сайте Edamam.com\n"
        "✓ Доступ к книге рецептов 1952 года\n"
        "× Генерация рецептов с ИИ\n"
        "× Советы по выбору блюд"
    ),
    SubscriptionTier.PREMIUM.value: (
        "✓ Все функции Standard\n"
        "✓ Генерация рецептов с ИИ\n"
        "✓ Персональные рекомендации\n"
        "✓ Советы по выбору блюд"
    )
}

# Функции для каждого уровня подписки
TIER_FEATURES = {
    SubscriptionTier.FREE.value: [
        feature.name for feature in PREMIUM_FEATURES.values() 
        if not feature.is_premium and not feature.is_standard
    ],
    SubscriptionTier.TRIAL.value: [
        feature.name for feature in PREMIUM_FEATURES.values()
    ],
    SubscriptionTier.STANDARD.value: [
        feature.name for feature in PREMIUM_FEATURES.values()
        if not feature.is_premium or feature.is_standard
    ],
    SubscriptionTier.PREMIUM.value: [
        feature.name for feature in PREMIUM_FEATURES.values()
    ]
}

# Конфигурация платежной системы
PAYMENT_CONFIG = {
    'currency': 'RUB',
    'timeout_minutes': 30,
    'success_url': 'https://your-bot-domain.com/success',
    'fail_url': 'https://your-bot-domain.com/fail'
}

# Путь к изображению с описанием тарифов
SUBSCRIPTION_IMAGE_PATH = "assets/subscription_plans.png"
