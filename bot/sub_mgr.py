# sub_mgr.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import TelegramError
from datetime import datetime
import logging
from typing import Dict, Any, Optional, List
from html import escape
from .sub_db import SubscriptionDB, DatabaseError
from .payment_system import PaymentSystem
from .subscription_config import (
    SubscriptionTier, 
    SUBSCRIPTION_DESCRIPTIONS, 
    PREMIUM_FEATURES, 
    FREE_LIMITS, 
    TRIAL_USER_LIMIT, 
    SUBSCRIPTION_PRICES_V1, 
    SUBSCRIPTION_PRICES_V2,
    ConversationStates
)

logger = logging.getLogger(__name__)

class SubscriptionError(Exception):
    """Базовый класс для ошибок подписки"""
    pass

class SubscriptionManager:
    def __init__(self, db: SubscriptionDB, payment_system: PaymentSystem):
        self.db = db
        self.payment_system = payment_system

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """
        Преобразование строки даты из SQLite в datetime
        """
        if not date_str:
            return None
        try:
            # Если date_str уже является объектом datetime, возвращаем его
            if isinstance(date_str, datetime):
                return date_str
            # Иначе преобразуем строку в datetime
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            logger.error(f"Некорректный формат даты: {date_str}", exc_info=True)
            return None

    def _format_date(self, dt: datetime) -> str:
        """
        Форматирование даты для вывода пользователю
        
        Args:
            dt: Объект datetime
            
        Returns:
            str: Отформатированная дата
        """
        return dt.strftime('%d.%m.%Y %H:%M')
    async def handle_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /profile - показывает информацию о текущей подписке"""
        try:
            user_id = update.effective_user.id
            subscription_info = self.db.get_user_subscription(user_id)

            if not subscription_info:
                await update.message.reply_text(
                    "У вас пока нет активной подписки.\n"
                    "Используйте /manage для оформления подписки."
                )
                return

            status_message = self._format_subscription_info(subscription_info)
            usage_info = self._get_feature_usage_info(user_id)
            final_message = f"{status_message}\n\n{usage_info}"
            
            keyboard = self._get_profile_keyboard(subscription_info)
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                final_message, 
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

        except DatabaseError as e:
            logger.error(f"Database error in handle_profile: {e}", exc_info=True)
            await update.message.reply_text(
                "Произошла ошибка при получении информации о подписке. "
                "Пожалуйста, попробуйте позже."
            )
        except Exception as e:
            logger.error(f"Unexpected error in handle_profile: {e}", exc_info=True)
            await update.message.reply_text(
                "Произошла непредвиденная ошибка. "
                "Пожалуйста, попробуйте позже."
            )
    async def handle_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /subscription - проверка статуса подписки"""
        try:
            user_id = update.effective_user.id
            subscription_info = self.db.get_user_subscription(user_id)

            if not subscription_info:
                keyboard = [[InlineKeyboardButton("Оформить подписку", callback_data="show_plans")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
                await update.message.reply_text(
                    "У вас нет активной подписки.\n"
                    "Используйте /manage для оформления подписки.",
                    reply_markup=reply_markup
                )
                return

            is_trial = subscription_info['is_trial']
            status = subscription_info['status']
            level = subscription_info['subscription_level']
        
            if is_trial:
                days_left = subscription_info.get('days_left', 0)
                message = (
                    "🎁 <b>Пробный период</b>\n\n"
                    f"Осталось дней: <b>{days_left}</b>\n"
                    "После окончания пробного периода необходимо выбрать подписку\n\n"
                    "📋 Доступные функции в пробном периоде:\n"
                )
                for feature, details in PREMIUM_FEATURES.items():
                    if details.is_standard:  # В пробном периоде доступны функции стандартной подписки
                        message += f"✅ {escape(details.description)}\n"
                    else:
                        message += f"❌ {escape(details.description)} (требуется Premium)\n"
            else:
                end_date = subscription_info.get('end_date')
                formatted_date = self._format_date(end_date) if end_date else "Не указано"
            
                if status == 'active':
                    message = (
                        f"✅ <b>Активная подписка {escape(level.capitalize())}</b>\n\n"
                        f"Действует до: <b>{formatted_date}</b>\n\n"
                        "📋 Доступные функции:\n"
                    )
                    for feature, details in PREMIUM_FEATURES.items():
                        if (details.is_premium and level == 'premium') or \
                            (details.is_standard and level in ['standard', 'premium']):
                            message += f"✅ {escape(details.description)}\n"
                        else:
                            message += f"❌ {escape(details.description)}\n"
                else:
                    message = (
                        "❌ <b>Подписка неактивна</b>\n\n"
                        "📋 Доступные бесплатные функции:\n"
                    )
                    for feature, limit in FREE_LIMITS.items():
                        usage = self.db.get_daily_feature_usage(user_id, feature)
                        message += f"• {escape(feature)}: {usage}/{limit} раз в день\n"

            keyboard = []
            if is_trial:
                keyboard.append([InlineKeyboardButton("Выбрать подписку", callback_data="show_plans")])
            elif status != 'active':
                keyboard.append([InlineKeyboardButton("Оформить подписку", callback_data="show_plans")])
            else:
                keyboard.append([InlineKeyboardButton("Управление подпиской", callback_data="show_plans")])
        
            reply_markup = InlineKeyboardMarkup(keyboard)
        
            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

        except Exception as e:
            logger.error(f"Error in handle_subscription: {e}", exc_info=True)
            await update.message.reply_text(
                "Произошла ошибка при проверке подписки. "
                "Пожалуйста, попробуйте позже."
            )
                
    async def handle_manage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработчик команды /manage - начало процесса управления подпиской"""
        try:
            user_id = update.effective_user.id
            
            if not self.db.get_user_subscription(user_id):
                success, _ = self.db.initialize_user(user_id)
                if not success:
                    raise DatabaseError("Failed to initialize user")

            total_users = self.db.get_total_users_count()
            prices = SUBSCRIPTION_PRICES_V1 if total_users <= TRIAL_USER_LIMIT else SUBSCRIPTION_PRICES_V2

            keyboard = [
                [InlineKeyboardButton("Стандартная подписка", callback_data="tier_standard")],
                [InlineKeyboardButton("Премиум подписка", callback_data="tier_premium")],
                [InlineKeyboardButton("Отмена", callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = (
                "🔄 <b>Управление подпиской</b>\n\n"
                "Выберите подходящий тариф:\n\n"
                "<b>Стандартная подписка</b>\n"
                f"<i>{escape(SUBSCRIPTION_DESCRIPTIONS['standard'])}</i>\n"
                f"От {min(prices['standard'].values())} руб/мес\n\n"
                "<b>Премиум подписка</b>\n"
                f"<i>{escape(SUBSCRIPTION_DESCRIPTIONS['premium'])}</i>\n"
                f"От {min(prices['premium'].values())} руб/мес"
            )

            await update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return ConversationStates.CHOOSING_TIER.value

        except DatabaseError as e:
            logger.error(f"Database error in handle_manage: {e}", exc_info=True)
            await update.message.reply_text(
                "Произошла ошибка при открытии меню подписок. "
                "Пожалуйста, попробуйте позже."
            )
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Unexpected error in handle_manage: {e}", exc_info=True)
            await update.message.reply_text(
                "Произошла непредвиденная ошибка. "
                "Пожалуйста, попробуйте позже."
            )
            return ConversationHandler.END
        
    async def handle_tier_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            query = update.callback_query
            await query.answer()
            
            if query.data == "cancel":
                await query.edit_message_text("Операция отменена")
                return ConversationHandler.END
            
            chosen_tier = query.data.split('_')[1]
            context.user_data['chosen_tier'] = chosen_tier

            total_users = self.db.get_total_users_count()
            prices = SUBSCRIPTION_PRICES_V1 if total_users <= TRIAL_USER_LIMIT else SUBSCRIPTION_PRICES_V2

            keyboard = []
            for duration in sorted(prices[chosen_tier].keys()):
                keyboard.append([InlineKeyboardButton(
                    f"{duration} мес. - {prices[chosen_tier][duration]} руб.",
                    callback_data=f"duration_{duration}"
                )])
            keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                current_text = query.message.text_html if query.message else ""
                message = (
                    f"🎯 Выбран тариф: <b>{escape(chosen_tier.capitalize())}</b>\n\n"
                    "Выберите длительность подписки:"
                )
                
                if message.strip() != current_text.strip():
                    try:
                        await query.edit_message_text(
                            text=message,
                            reply_markup=reply_markup,
                            parse_mode='HTML'
                        )
                    except TelegramError as e:
                        if "Bad Request" in str(e):
                            await query.message.reply_text(
                                text=message,
                                reply_markup=reply_markup,
                                parse_mode='HTML'
                            )
                
            except TelegramError as e:
                if "message is not modified" not in str(e).lower():
                    raise
                
            return ConversationStates.CHOOSING_DURATION.value

        except Exception as e:
            logger.error(f"Error in handle_tier_choice: {e}", exc_info=True)
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    "Произошла ошибка при выборе тарифа. Попробуйте позже."
                )
            return ConversationHandler.END
        
    async def handle_duration_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора длительности подписки"""
        try:
            query = update.callback_query
            await query.answer()

            if query.data == "cancel":
                await query.edit_message_text("Оформление подписки отменено.")
                return ConversationHandler.END

            user_id = update.effective_user.id
            duration = int(query.data.split('_')[1])
            tier = context.user_data.get('chosen_tier')
            
            if not tier:
                await query.edit_message_text("Ошибка: не выбран тариф. Начните сначала.")
                return ConversationHandler.END

            total_users = self.db.get_total_users_count()
            prices = SUBSCRIPTION_PRICES_V1 if total_users <= TRIAL_USER_LIMIT else SUBSCRIPTION_PRICES_V2
            amount = prices[tier][duration]

            description = f"Подписка {tier.capitalize()} на {duration} мес."
            
            try:
                payment_info = self.payment_system.create_payment(
                    amount=amount,
                    description=description,
                    user_id=user_id,
                    subscription_type=tier,
                    duration=duration,
                    return_url=f"https://t.me/ShefRecept_bot?start=payment_{user_id}"
                )
            
                if not payment_info or not self.db.add_payment_record(user_id, payment_info):
                    raise DatabaseError("Failed to add payment record")
                
                keyboard = [
                    [InlineKeyboardButton("Оплатить", url=payment_info['confirmation_url'])],
                    [InlineKeyboardButton("Проверить оплату", callback_data="check_payment")],
                    [InlineKeyboardButton("Отменить", callback_data="cancel_payment")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    f"💳 <b>Оплата подписки</b>\n\n"
                    f"Тариф: <b>{escape(tier.capitalize())}</b>\n"
                    f"Длительность: <b>{duration} мес.</b>\n"
                    f"Стоимость: <b>{amount} руб.</b>\n\n"
                    f"Для оплаты нажмите кнопку ниже.\n"
                    f"После оплаты нажмите 'Проверить оплату'",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                
                context.user_data.update({
                    'payment_id': payment_info['payment_id'],
                    'duration': str(duration),
                    'tier': tier
                })
                return ConversationStates.CHECKING_PAYMENT.value

            except Exception as e:
                logger.error(f"Payment creation error: {e}", exc_info=True)
                await query.edit_message_text(
                    "Ошибка при создании платежа. Попробуйте позже."
                )
                return ConversationHandler.END

        except Exception as e:
            logger.error(f"Duration choice error: {e}", exc_info=True)
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    "Произошла ошибка. Попробуйте позже."
                )
            return ConversationHandler.END
    async def check_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        try:
            query = update.callback_query
            if query:
                await query.answer()

            payment_id = context.user_data.get('payment_id')
            if not payment_id:
                message = "❌ Платёж не найден. Начните оформление подписки заново."
                if query:
                    try:
                        await query.edit_message_text(
                            message,
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("Начать заново", callback_data="show_plans")
                            ]])
                        )
                    except TelegramError as e:
                        if "message is not modified" not in str(e).lower():
                            raise
                else:
                    await update.message.reply_text(message)
                return ConversationHandler.END

            payment_status = self.payment_system.check_payment_status(payment_id)
        
            if payment_status['status'] == 'succeeded':
                user_id = update.effective_user.id
                tier = context.user_data.get('tier')
                duration = int(context.user_data.get('duration', 0))
            
                if not all([tier, duration]):
                    raise ValueError("Missing subscription details")

                if self.db.update_subscription(user_id, tier, duration):
                    subscription_info = self.db.get_user_subscription(user_id)
                    end_date = self._parse_date(subscription_info['end_date'])
                    formatted_date = self._format_date(end_date) if end_date else "Не указано"
                
                    success_message = (
                        f"✅ <b>Подписка успешно оформлена!</b>\n\n"
                        f"Тариф: <b>{escape(tier.capitalize())}</b>\n"
                        f"Длительность: <b>{duration} мес.</b>\n"
                        f"Действует до: <b>{escape(formatted_date)}</b>\n\n"
                        "Используйте /profile для просмотра деталей подписки"
                    )
                    if query:
                        await query.edit_message_text(success_message, parse_mode='HTML')
                    else:
                        await update.message.reply_text(success_message, parse_mode='HTML')
                    return ConversationHandler.END
                else:
                    raise DatabaseError("Failed to update subscription")
            else:
                wait_message = (
                    "⏳ Платёж ещё не завершён.\n"
                    "Пожалуйста, завершите оплату и повторите проверку."
                )
                keyboard = [
                    [InlineKeyboardButton("Проверить снова", callback_data="check_payment")],
                    [InlineKeyboardButton("Отменить", callback_data="cancel_payment")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
                if query:
                    try:
                        await query.edit_message_text(
                            wait_message,
                            reply_markup=reply_markup
                        )
                    except TelegramError as e:
                        if "message is not modified" not in str(e).lower():
                            raise
                else:
                    await update.message.reply_text(
                        wait_message,
                        reply_markup=reply_markup
                    )
                return ConversationStates.CHECKING_PAYMENT.value

        except Exception as e:
            logger.error(f"Payment check error: {e}", exc_info=True)
            error_message = "Произошла ошибка при проверке платежа. Обратитесь в поддержку."
            if update.callback_query:
                await update.callback_query.message.reply_text(error_message)
            else:
                await update.message.reply_text(error_message)
            return ConversationHandler.END
    def _format_subscription_info(self, subscription_info: Dict[str, Any]) -> str:
        """
        Форматирование информации о подписке
        """
        if not subscription_info:
            return "❌ Информация о подписке не найдена"

        status = subscription_info['status']
        level = subscription_info['subscription_level']
        is_trial = subscription_info.get('is_trial', 0)
    
        if is_trial:
            status_text = "Пробный период"
        else:
            status_text = {
                'active': 'Активная',
                'trial': 'Пробный период',
                'expired': 'Истекла',
                'free': 'Базовая'
            }.get(status, status)

        end_date = self._parse_date(subscription_info.get('end_date'))
        if end_date:
            days_left = (end_date - datetime.now()).days
            if days_left > 0:
                date_text = f"{self._format_date(end_date)} (осталось {days_left} дней)"
            else:
                date_text = "Истекла"
        else:
            date_text = "Не указано"

        message = (
            f"📊 <b>Информация о подписке</b>\n\n"
            f"Текущий статус: <b>{escape(status_text)}</b>\n"
        )

        if is_trial:
            message += (
                f"У вас активирован пробный период на 14 дней\n"
                f"Действует до: <b>{date_text}</b>\n\n"
                "После окончания пробного периода необходимо выбрать подписку\n"
                "для продолжения использования расширенных функций."
            )
        else:
            message += (
                f"Уровень подписки: <b>{escape(level.capitalize())}</b>\n"
                f"Действует до: <b>{date_text}</b>\n"
            )

        return message
    
    def _get_feature_usage_info(self, user_id: int) -> str:
        """
        Получение информации об использовании функций
        
        Args:
            user_id: ID пользователя
            
        Returns:
            str: Отформатированное сообщение
        """
        message = "📈 <b>Использование функций сегодня</b>\n\n"
        
        try:
            for feature, limit in FREE_LIMITS.items():
                usage = self.db.get_daily_feature_usage(user_id, feature)
                status = '✅' if usage < limit else '❌'
                message += f"{status} {escape(feature)}: <b>{usage}/{limit}</b>\n"
                
        except DatabaseError as e:
            logger.error(f"Error getting feature usage: {e}", exc_info=True)
            message += "<i>Ошибка получения статистики</i>\n"
            
        return message

    def _get_profile_keyboard(self, subscription_info: Dict[str, Any]) -> List[List[InlineKeyboardButton]]:
        """
        Создание клавиатуры для профиля
        
        Args:
            subscription_info: Информация о подписке
            
        Returns:
            List[List[InlineKeyboardButton]]: Клавиатура
        """
        keyboard = []
        
        status = subscription_info.get('status')
        if status == 'active':
            end_date = self._parse_date(subscription_info.get('end_date'))
            if end_date and (end_date - datetime.now()).days <= 7:
                keyboard.append([
                    InlineKeyboardButton("Продлить подписку", callback_data="show_plans")
                ])
        elif status in ['expired', 'free', 'trial']:
            keyboard.append([
                InlineKeyboardButton("Оформить подписку", callback_data="show_plans")
            ])
        
        if subscription_info.get('payment_id'):
            keyboard.append([
                InlineKeyboardButton("Проверить платеж", callback_data="check_payment")
            ])
            
        return keyboard

    async def check_access(self, user_id: int, feature: str) -> bool:
        """
        Проверка доступа к функции
        
        Args:
            user_id: ID пользователя
            feature: Название функции
            
        Returns:
            bool: True если доступ разрешен
        """
        try:
            subscription_info = self.db.get_user_subscription(user_id)
            if not subscription_info:
                return False
                
            feature_info = PREMIUM_FEATURES.get(feature)
            if not feature_info:
                logger.warning(f"Unknown feature requested: {feature}")
                return False
                
            subscription_level = subscription_info['subscription_level']
            subscription_status = subscription_info['status']

            # Проверяем активность подписки
            if subscription_status not in ['active', 'trial']:
                return False

            # Для премиум функций
            if feature_info.is_premium:
                return subscription_level == 'premium'
                
            # Для стандартных функций
            if feature_info.is_standard:
                return subscription_level in ['standard', 'premium']
                
            # Для бесплатных функций проверяем лимиты
            daily_limit = FREE_LIMITS.get(feature, 0)
            if not daily_limit:
                return False
                
            daily_usage = self.db.get_daily_feature_usage(user_id, feature)
            return daily_usage < daily_limit
            
        except DatabaseError as e:
            logger.error(f"Database error in check_access: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error in check_access: {e}", exc_info=True)
            return False
    