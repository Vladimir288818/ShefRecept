#subscription.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.sub_db import SubscriptionDB
from .subscription_config import (
    SubscriptionTier,
    TRIAL_USER_LIMIT,
    SUBSCRIPTION_PRICES_V1,
    SUBSCRIPTION_PRICES_V2,
    SUBSCRIPTION_DESCRIPTIONS
)
import logging
from datetime import datetime
import os

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализация базы данных подписок
db_path = r"C:/Users/Dell/Desktop/culinary_bot/subscriptions.db"
subscription_db = SubscriptionDB(db_path)

class SubscriptionManager:
    def __init__(self, db: SubscriptionDB):
        """Инициализация менеджера подписок"""
        self.db = db

    async def show_subscription_plans(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показ доступных планов подписки"""
        try:
            query = update.callback_query
            user_id = update.effective_user.id
            
            # Получаем количество пользователей для определения версии цен
            user_count = self.db.get_total_users_count()
            prices = SUBSCRIPTION_PRICES_V1 if user_count <= TRIAL_USER_LIMIT else SUBSCRIPTION_PRICES_V2
            
            keyboard = []
            for tier in [SubscriptionTier.STANDARD, SubscriptionTier.PREMIUM]:
                price = prices[tier.value][1]  # Цена за 1 месяц
                button = InlineKeyboardButton(
                    f"{tier.value.title()} - {price}₽/мес",
                    callback_data=f"tier_{tier.value}"
                )
                keyboard.append([button])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.answer()
            await query.edit_message_text(
                "Выберите тариф подписки:\n\n" + 
                "\n\n".join([
                    f"{tier.value.title()}:\n{SUBSCRIPTION_DESCRIPTIONS[tier.value]}"
                    for tier in [SubscriptionTier.STANDARD, SubscriptionTier.PREMIUM]
                ]),
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Ошибка в show_subscription_plans: {e}")
            if query:
                await query.answer("Произошла ошибка при загрузке планов подписки")

    async def handle_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /profile"""
        user_id = update.effective_user.id
        try:
            subscription_info = self.db.get_user_subscription(user_id)
            if subscription_info:
                level = subscription_info["subscription_level"]
                subscription_end_date = subscription_info["end_date"]

                if level == SubscriptionTier.FREE.value:
                    message = f"Ваш уровень подписки: {level}."
                else:
                    remaining_days = (datetime.fromisoformat(subscription_end_date) - datetime.now()).days
                    message = f"Ваш уровень подписки: {level}. Подписка истекает через {remaining_days} дней."
                await update.message.reply_text(message)
            else:
                await update.message.reply_text("Ошибка при получении информации о подписке.")
        except Exception as e:
            logger.error(f"Ошибка в handle_profile: {e}")
            await update.message.reply_text("Произошла ошибка при получении информации о подписке. Попробуйте позже.")

    async def handle_manage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /manage"""
        user_id = update.effective_user.id
        if len(context.args) < 2:
            await update.message.reply_text("Использование: /manage <уровень> <длительность в месяцах>")
            return

        level = context.args[0].lower()
        duration = context.args[1]

        valid_levels = {tier.value for tier in SubscriptionTier}
        if level not in valid_levels:
            await update.message.reply_text(f"Неверный уровень подписки. Доступные уровни: {', '.join(valid_levels)}.")
            return

        try:
            duration = int(duration)
            if duration <= 0:
                raise ValueError("Длительность должна быть положительным числом.")

            updated = self.db.update_subscription(user_id, level, duration)
            if updated:
                await update.message.reply_text(f"Подписка '{level}' успешно обновлена на {duration} месяцев.")
            else:
                await update.message.reply_text("Ошибка при обновлении подписки. Попробуйте позже.")
        except ValueError:
            await update.message.reply_text("Длительность должна быть числом.")
        except Exception as e:
            logger.error(f"Ошибка в handle_manage: {e}")
            await update.message.reply_text("Произошла ошибка при управлении подпиской. Попробуйте позже.")

    async def handle_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /subscription"""
        user_id = update.effective_user.id
        try:
            if self.db.check_subscription_status(user_id):
                await update.message.reply_text("У вас активная подписка. Все функции бота доступны.")
            else:
                await update.message.reply_text("У вас нет активной подписки. Некоторые функции могут быть недоступны.")
        except Exception as e:
            logger.error(f"Ошибка в handle_subscription: {e}")
            await update.message.reply_text("Произошла ошибка при проверке статуса подписки. Попробуйте позже.")

    async def initialize_user(self, user_id: int) -> None:
        """Инициализация нового пользователя"""
        try:
            if not self.db.get_user_subscription(user_id):
                self.db.create_user_subscription(user_id, SubscriptionTier.FREE.value)
                logger.info(f"Создана бесплатная подписка для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка при инициализации пользователя {user_id}: {e}")

    def check_feature_access(self, user_id: int, feature: str) -> bool:
        """Проверка доступа к функции"""
        try:
            subscription_info = self.db.get_user_subscription(user_id)
            if not subscription_info:
                return False
                
            level = subscription_info["subscription_level"]
            subscription_end_date = subscription_info.get("end_date")
            
            # Для бесплатного уровня
            if level == SubscriptionTier.FREE.value:
                return feature in TIER_FEATURES[SubscriptionTier.FREE.value]
                
            # Проверка срока действия для платных подписок
            if subscription_end_date:
                if datetime.fromisoformat(subscription_end_date) < datetime.now():
                    return False
                    
            return feature in TIER_FEATURES[level]
            
        except Exception as e:
            logger.error(f"Ошибка при проверке доступа к функции {feature} для пользователя {user_id}: {e}")
            return False