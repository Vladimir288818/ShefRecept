from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.sub_db import SubscriptionDB
import logging

logger = logging.getLogger(__name__)

class SubscriptionManager:
    def __init__(self, db: SubscriptionDB):
        self.db = db

    async def handle_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /profile"""
        # Реализация осталась без изменений

    async def handle_manage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /manage"""
        user_id = update.effective_user.id
        subscription_info = self.db.get_user_subscription(user_id)

        if subscription_info:
            level = subscription_info.get("level", "free")
        else:
            # Инициализируем нового пользователя с бесплатной подпиской
            self.db.initialize_user(user_id)
            level = "free"

        keyboard = [
            [InlineKeyboardButton("Стандартная подписка (ограниченный доступ)", callback_data=f"subscribe_standard")],
            [InlineKeyboardButton("Премиум подписка (без ограничений)", callback_data=f"subscribe_premium")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = f"Выберите уровень подписки:\n\n"
        if level == "free":
            message += "Вы сейчас используете бесплатную подписку."
        elif level == "standard":
            message += "Вы сейчас используете стандартную подписку."
        elif level == "premium":
            message += "Вы сейчас используете премиум подписку."

        await update.message.reply_text(message, reply_markup=reply_markup)

    async def handle_subscription_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик нажатия на кнопку подписки"""
        query = update.callback_query
        user_id = update.effective_user.id
        action = query.data.split("_")[1]

        if action == "standard":
            if self.db.update_subscription(user_id, "standard", 1):
                await query.answer("Подписка на стандартный уровень успешно оформлена!")
            else:
                await query.answer("Не удалось обновить подписку. Попробуйте позже.")
        elif action == "premium":
            if self.db.update_subscription(user_id, "premium", 1):
                await query.answer("Подписка на премиум уровень успешно оформлена!")
            else:
                await query.answer("Не удалось обновить подписку. Попробуйте позже.")

        await query.message.delete()

    async def handle_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /subscription"""
        # Реализация осталась без изменений