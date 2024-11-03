# subscription.py - Логика работы с подписками

from telegram import Update
from telegram.ext import ContextTypes
from bot.subscription_db import SubscriptionDB
import logging
from datetime import datetime

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализация базы данных подписок (путь к базе данных необходимо корректировать в соответствии с вашим окружением)
db_path = "C:/Users/WIN10/Desktop/culinary_bot/bot/subscriptions.db"
subscription_db = SubscriptionDB(db_path)

class SubscriptionManager:
    def __init__(self, db: SubscriptionDB):
        """Инициализация менеджера подписок"""
        self.db = db

    async def handle_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /profile"""
        user_id = update.effective_user.id
        try:
            subscription_info = self.db.get_user_subscription(user_id)
            if subscription_info:
                level = subscription_info["level"]
                trial_recipes_left = subscription_info["trial_recipes_left"]
                subscription_end_date = subscription_info["subscription_end_date"]

                if level == "free":
                    message = f"Ваш уровень подписки: {level}. Осталось пробных рецептов: {trial_recipes_left}."
                else:
                    remaining_days = (datetime.strptime(subscription_end_date, "%Y-%m-%d %H:%M:%S") - datetime.now()).days
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

        valid_levels = {"standard", "premium"}
        if level not in valid_levels:
            await update.message.reply_text("Неверный уровень подписки. Доступные уровни: standard, premium.")
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
            success, trial_recipes_left = self.db.reduce_trial_recipes(user_id)
            if success:
                await update.message.reply_text(f"Вы использовали пробный рецепт. Осталось {trial_recipes_left} пробных рецептов.")
            else:
                await update.message.reply_text("Ваш пробный лимит исчерпан. Пожалуйста, оформите подписку для доступа к большему количеству рецептов.")
        except Exception as e:
            logger.error(f"Ошибка в handle_subscription: {e}")
            await update.message.reply_text("Произошла ошибка при использовании пробных рецептов. Попробуйте позже.")
