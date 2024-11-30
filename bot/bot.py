#bot.py
import os
import sys
import asyncio
import logging
import signal
from typing import Optional, Dict, Any, Callable
from pathlib import Path
from datetime import datetime, timedelta
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import PicklePersistence 
from telegram.error import Conflict, NetworkError, TelegramError
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    ConversationHandler, 
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv
from aiohttp import web

from .database import Database
from .ai_module import get_openai_response
from .web_search import RecipeParser
from .user_activity import log_user_interaction, get_users_count, create_users_table
from .calories import calculate_calories
from .sub_mgr import SubscriptionManager
from .sub_db import SubscriptionDB, DatabaseError
from .ai_assistant import AIAssistant
from .yookassa_payment import YooKassaPayment
from .subscription_config import (
    PREMIUM_FEATURES,
    SUBSCRIPTION_PRICES_V1,
    SUBSCRIPTION_PRICES_V2,
    SubscriptionTier,
    TRIAL_USER_LIMIT,
    ConversationStates
)

load_dotenv()

ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

class ConversationState:
    WAITING_FOR_RECIPE = 0
    AI_RECIPE = 1
    WAITING_FOR_RECIPE_SEARCH = 2
    WAITING_FOR_CALORIES = 3
    WAITING_FOR_ASSISTANT_RESPONSE = 4

ai_assistant = None
subscription_db = None
yookassa_payment = None
subscription_manager = None
recipe_db = None
def check_bot_instance():
    pid_file = Path("bot.pid")
    
    if pid_file.exists():
        try:
            with open(pid_file) as f:
                old_pid = int(f.read())
            try:
                os.kill(old_pid, 0)
                logger.critical(f"Бот уже запущен (PID: {old_pid})")
                return False
            except OSError:
                pass
        except (ValueError, IOError) as e:
            logger.error(f"Ошибка чтения PID файла: {e}")
    
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except IOError as e:
        logger.error(f"Ошибка записи PID файла: {e}")
        return False

def cleanup():
    try:
        pid_file = Path("bot.pid")
        if pid_file.exists():
            pid_file.unlink()
        logger.info("Бот остановлен, ресурсы очищены")
    except Exception as e:
        logger.error(f"Ошибка при очистке: {e}")

async def handle_yookassa_webhook(request):
    try:
        data = await request.json()
        logger.info(f"Received webhook from YooKassa: {data}")
        
        if data.get('event') != 'payment.succeeded':
            logger.info(f"Ignored webhook event: {data.get('event')}")
            return web.Response(status=200)

        payment_info = data.get('object', {})
        metadata = payment_info.get('metadata', {})
        
        user_id = int(metadata.get('user_id'))
        subscription_type = metadata.get('subscription_type')
        duration = int(metadata.get('duration'))
        
        if all([user_id, subscription_type, duration]):
            success = subscription_db.update_subscription(user_id, subscription_type, duration)
            if success:
                logger.info(f"Subscription updated for user {user_id}")
            else:
                logger.error(f"Failed to update subscription for user {user_id}")
        
        return web.Response(status=200)
        
    except Exception as e:
        logger.error(f"Error processing YooKassa webhook: {e}")
        return web.Response(status=500)

async def start_webhook_server():
    app = web.Application()
    app.router.add_post('/webhook/yookassa', handle_yookassa_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    logger.info("Webhook server started")
def initialize_systems() -> tuple[SubscriptionDB, YooKassaPayment, SubscriptionManager]:
    try:
        logger.info("Starting systems initialization...")
        
        data_dir = Path("data").resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        
        required_env_vars = {
            "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
            "YOOKASSA_SHOP_ID": os.getenv("YOOKASSA_SHOP_ID"),
            "YOOKASSA_SECRET_KEY": os.getenv("YOOKASSA_SECRET_KEY")
        }
        
        missing_vars = [var for var, value in required_env_vars.items() if not value]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

        db_path = data_dir / "subscriptions.db"
        subscription_db = SubscriptionDB(str(db_path))
        logger.info("Database initialized successfully")
        
        yookassa_payment = YooKassaPayment()
        logger.info("YooKassa payment system initialized successfully")
        
        global ai_assistant
        ai_assistant = AIAssistant()
        logger.info("AI Assistant initialized successfully")
        
        subscription_manager = SubscriptionManager(
            db=subscription_db,
            payment_system=yookassa_payment
        )
        logger.info("Subscription manager initialized successfully")
        
        create_users_table()
        logger.info("User database initialized successfully")

        global recipe_db
        recipe_db = Database()
        logger.info("Recipe database initialized successfully")
        
        return subscription_db, yookassa_payment, subscription_manager
    except Exception as e:
        logger.error(f"Failed to initialize systems: {e}")
        raise

async def error_handler(update: Optional[Update], context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception while handling an update: {context.error}")

    try:
        if isinstance(context.error, Conflict):
            logger.critical("Конфликт: обнаружен другой экземпляр бота")
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ Обнаружен конфликт: бот уже запущен в другом процессе."
                )
            cleanup()
            sys.exit(1)
            
        elif isinstance(context.error, NetworkError):
            logger.error(f"Network error: {context.error}")
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "Произошла ошибка сети. Пожалуйста, попробуйте позже."
                )
        else:
            logger.error(f"Update {update} caused error {context.error}")
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
                )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")
async def get_advice_response(prompt: str) -> Optional[str]:
    if not ai_assistant:
        logger.error("AI Assistant not initialized")
        return None
    return await ai_assistant.get_advice_response(prompt)

def check_subscription(feature: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
            if not update.effective_user:
                return
                
            try:
                user_id = update.effective_user.id
                logger.info(f"Checking access for user {user_id} to feature {feature}")
                
                if not subscription_manager:
                    logger.error("Subscription manager not initialized")
                    await update.message.reply_text(
                        "Сервис временно недоступен. Попробуйте позже."
                    )
                    return

                if not await subscription_manager.check_access(user_id, feature):
                    keyboard = [
                        [InlineKeyboardButton("Оформить подписку", callback_data="show_plans")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(
                        "⚠️ Эта функция доступна только для подписчиков.\n"
                        "Используйте /manage для оформления подписки или нажмите кнопку ниже:",
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                    return
                
                return await func(update, context)
                
            except Exception as e:
                logger.error(f"Error in subscription check: {e}")
                await update.message.reply_text(
                    "Произошла ошибка при проверке доступа. Попробуйте позже."
                )
                return
        return wrapper
    return decorator

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
        
    try:
        user_id = update.effective_user.id
        user_name = escape(update.effective_user.full_name)
        logger.info(f"Starting conversation with user {user_id} ({user_name})")
        
        if not subscription_db:
            logger.error("Subscription database not initialized")
            await update.message.reply_text(
                "Сервис временно недоступен. Попробуйте позже."
            )
            return

        log_user_interaction(user_id)
        success, is_special_price = subscription_db.initialize_user(user_id)
        
        if not success:
            raise DatabaseError("Failed to initialize user")
        
        welcome_message = (
            f"👋 Добро пожаловать, <b>{user_name}</b>!\n\n"
            "🔍 Я помогу вам:\n"
            "• Найти рецепты из книги 1952 года\n"
            "• Сгенерировать новые рецепты с помощью ИИ\n"
            "• Рассчитать калорийность блюд\n"
            "• Получить персональные рекомендации\n\n"
            f"{'🎉 Для вас действуют специальные цены!' if is_special_price else ''}\n\n"
            "Используйте /help для просмотра всех команд."
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Тарифы", callback_data="show_plans")],
            [InlineKeyboardButton("▶️ Начать", callback_data="start")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message, 
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        logger.info(f"Welcome message sent to user {user_id}")
        
    except DatabaseError as e:
        logger.error(f"Database error in start command for user {user_id}: {e}")
        await update.message.reply_text(
            "Произошла ошибка при инициализации. Пожалуйста, попробуйте позже."
        )
    except Exception as e:
        logger.error(f"Unexpected error in start command for user {user_id}: {e}")
        await update.message.reply_text(
            "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
        )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
        
    try:
        user_id = update.effective_user.id
        logger.info(f"Help command requested by user {user_id}")
        
        if not subscription_db:
            logger.error("Subscription database not initialized")
            await update.message.reply_text(
                "Сервис временно недоступен. Попробуйте позже."
            )
            return

        commands = [
            "📝 <b>Основные команды:</b>",
            "/start - Начало работы с ботом",
            "/help - Помощь и справка",
            "",
            "🔍 <b>Поиск рецептов:</b>",
            "/recipes - Поиск рецептов по названию",
            "/web_search - Поиск рецептов на сайтах",
            "",
            "🤖 <b>ИИ и рекомендации:</b>",
            "/ai_recipes - Генерация рецептов с помощью ИИ",
            "/ai_assistant - Совет по выбору блюда или меню",
            "",
            "📊 <b>Дополнительные функции:</b>",
            "/calories - Рассчитать калорийность блюда",
            "/user_stats - Статистика использования",
            "",
            "💳 <b>Управление подпиской:</b>",
            "/profile - Просмотр статуса подписки",
            "/manage - Управление подпиской",
            "/subscription - Проверка доступа"
        ]
        
        subscription_info = subscription_db.get_user_subscription(user_id)
        if subscription_info:
            commands.append("\n✨ <b>Доступные функции:</b>")
            for feature, details in PREMIUM_FEATURES.items():
                is_available = (
                    details.is_premium and subscription_info['subscription_level'] == 'premium'
                ) or (
                    details.is_standard and subscription_info['subscription_level'] in ['standard', 'premium']
                )
                status = "✅" if is_available else "❌"
                commands.append(f"{status} {escape(details.description)}")
        
        await update.message.reply_text(
            "\n".join(commands), 
            parse_mode='HTML'
        )
        logger.info(f"Help message sent to user {user_id}")
        
    except DatabaseError as e:
        logger.error(f"Database error in help command for user {user_id}: {e}")
        await update.message.reply_text(
            "Произошла ошибка при получении информации. Попробуйте позже."
        )
    except Exception as e:
        logger.error(f"Error in help command for user {user_id}: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже."
        )
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END
        
    try:
        user_id = update.effective_user.id
        logger.info(f"Conversation cancelled by user {user_id}")
        
        cancel_message = (
            "✖️ Операция отменена.\n"
            "Используйте команды из /help для продолжения работы."
        )
        
        if update.callback_query:
            await update.callback_query.message.reply_text(
                cancel_message,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                cancel_message,
                parse_mode='HTML'
            )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in cancel handler: {e}")
        return ConversationHandler.END

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
        
    user_id = update.effective_user.id
    
    # Проверка на администратора
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(
            "У вас нет доступа к этой команде."
        )
        return
        
    try:
        logger.info(f"Admin stats requested by user {user_id}")
        
        # Статистика за последние 30 дней
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
        user_count = get_users_count(start_date, end_date)
        
        # Получаем статистику по подпискам
        total_users = subscription_db.get_total_users_count()
        active_premium = subscription_db.get_subscription_count('premium')
        active_standard = subscription_db.get_subscription_count('standard')
        trial_users = subscription_db.get_trial_users_count()
        
        stats_message = (
            "📊 <b>Статистика бота</b>\n\n"
            f"Всего пользователей: <b>{total_users}</b>\n"
            f"Активных за 30 дней: <b>{user_count}</b>\n\n"
            f"Premium подписки: <b>{active_premium}</b>\n"
            f"Standard подписки: <b>{active_standard}</b>\n"
            f"Пробный период: <b>{trial_users}</b>\n"
            f"Бесплатных пользователей: <b>{total_users - active_premium - active_standard - trial_users}</b>\n"
        )
        
        await update.message.reply_text(
            stats_message,
            parse_mode='HTML'
        )
        logger.info(f"Admin stats sent to user {user_id}")
        
    except DatabaseError as e:
        logger.error(f"Database error in admin stats for user {user_id}: {e}")
        await update.message.reply_text(
            "Произошла ошибка при получении статистики. Попробуйте позже."
        )
    except Exception as e:
        logger.error(f"Error in admin stats for user {user_id}: {e}")
        await update.message.reply_text(
            "Произошла ошибка при получении статистики. Попробуйте позже."
        )
async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not subscription_manager:
        logger.error("Subscription manager not initialized")
        await update.message.reply_text("Сервис временно недоступен")
        return
    await subscription_manager.handle_profile(update, context)

async def handle_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not subscription_manager:
        logger.error("Subscription manager not initialized")
        await update.message.reply_text("Сервис временно недоступен")
        return
    await subscription_manager.handle_subscription(update, context)

@check_subscription('recipes_1952')
async def recipes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END

    try:
        user_id = update.effective_user.id
        logger.info(f"Recipe search initiated by user {user_id}")
        
        if not subscription_db:
            logger.error("Subscription database not initialized")
            await update.message.reply_text("Сервис временно недоступен")
            return ConversationHandler.END

        subscription_db.track_feature_usage(user_id, 'recipes_1952')
        
        keyboard = [
            [InlineKeyboardButton("Отмена", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔍 <b>Поиск рецептов в книге о вкусной и здоровой пище 1952 года</b>\n\n"
            "Введите название рецепта для поиска:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return ConversationState.WAITING_FOR_RECIPE
        
    except Exception as e:
        logger.error(f"Error in recipes command: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже."
        )
        return ConversationHandler.END

async def search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END

    user_id = update.effective_user.id
    try:
        recipe_name = update.message.text
        logger.info(f"User {user_id} searching for recipe: {recipe_name}")

        closest_recipe_name = recipe_db.fuzzy_search_recipe_by_name(recipe_name)
        if not closest_recipe_name:
            logger.info(f"No recipe found for query: {recipe_name}")
            await update.message.reply_text(
                "❌ Рецепт не найден.\n"
                "Попробуйте изменить запрос или использовать другое название."
            )
            return ConversationHandler.END
        recipe = recipe_db.get_recipe_by_name(closest_recipe_name)

        if not recipe:
            logger.warning(f"Failed to get recipe details for: {closest_recipe_name}")
            raise DatabaseError("Failed to retrieve recipe details")

        message = (
            f"📖 <b>{escape(recipe[0])}</b>\n\n"
            f"🥘 <b>Ингредиенты:</b>\n{escape(recipe[1])}\n\n"
            f"👩‍🍳 <b>Инструкции:</b>\n{escape(recipe[2])}"
        )
        
        keyboard = [
            [InlineKeyboardButton("Рассчитать калории", callback_data=f"calories_{recipe[0]}")],
            [InlineKeyboardButton("Найти другой рецепт", callback_data="search_again")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message, 
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        logger.info(f"Recipe {closest_recipe_name} sent to user {user_id}")
        return ConversationHandler.END

    except DatabaseError as e:
        logger.error(f"Database error in recipe search for user {user_id}: {e}")
        await update.message.reply_text(
            "Произошла ошибка при поиске рецепта в базе данных. "
            "Пожалуйста, попробуйте позже."
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in recipe search for user {user_id}: {e}")
        await update.message.reply_text(
            "Произошла непредвиденная ошибка при поиске рецепта."
        )
        return ConversationHandler.END

@check_subscription('ai_recipes')
async def ai_recipes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END
        
    try:
        user_id = update.effective_user.id
        logger.info(f"AI recipe generation requested by user {user_id}")
        
        if not subscription_db:
            logger.error("Subscription database not initialized")
            await update.message.reply_text("Сервис временно недоступен")
            return ConversationHandler.END

        subscription_db.track_feature_usage(user_id, 'ai_recipes')
        
        keyboard = [
            [InlineKeyboardButton("Отмена", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 <b>Генерация рецептов с помощью ИИ</b>\n\n"
            "Опишите желаемое блюдо или укажите ингредиенты.\n"
            "Например:\n"
            "• Вегетарианское блюдо из тыквы\n"
            "• Быстрый десерт без выпечки\n"
            "• Блюдо из курицы, риса и овощей",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return ConversationState.AI_RECIPE
        
    except Exception as e:
        logger.error(f"Error in ai_recipes command: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже."
        )
        return ConversationHandler.END

async def handle_ai_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END

    user_id = update.effective_user.id
    try:
        user_message = update.message.text
        logger.info(f"Processing AI recipe request from user {user_id}: {user_message}")

        await update.message.reply_chat_action("typing")

        prompt = f"Предложи рецепт на основе запроса: {user_message}"
        recipe = await get_openai_response(prompt)

        if not recipe:
            raise Exception("Failed to generate recipe")

        keyboard = [
            [InlineKeyboardButton("Сгенерировать ещё", callback_data="generate_again")],
            [InlineKeyboardButton("Рассчитать калории", callback_data="calculate_calories")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"👨‍🍳 <b>Сгенерированный рецепт:</b>\n\n{escape(recipe)}",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        logger.info(f"AI recipe generated successfully for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in AI recipe generation for user {user_id}: {e}")
        await update.message.reply_text(
            "❌ Извините, произошла ошибка при генерации рецепта.\n"
            "Пожалуйста, попробуйте еще раз или измените запрос."
        )
    
    return ConversationHandler.END

@check_subscription('calculate_calories')
async def handle_calories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /calories command."""
    await update.message.reply_text("Вставьте список ингредиентов с количеством для расчета калорийности:")
    return ConversationState.WAITING_FOR_CALORIES

async def calculate_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Calculate calories based on ingredients provided."""
    ingredients = update.message.text
    try:
        response = await calculate_calories(ingredients)
        await update.message.reply_text(response if response else "Не удалось рассчитать калорийность.")
    except Exception as e:
        logger.error(f"Error in calculating calories: {e}")
        await update.message.reply_text("Произошла ошибка при расчете калорийности.")
    return ConversationHandler.END

@check_subscription('ai_assistant')
async def ai_assistant_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END
        
    try:
        user_id = update.effective_user.id
        logger.info(f"AI assistant requested by user {user_id}")
        
        if not subscription_db:
            logger.error("Subscription database not initialized")
            await update.message.reply_text("Сервис временно недоступен")
            return ConversationHandler.END

        subscription_db.track_feature_usage(user_id, 'ai_assistant')
        
        keyboard = [
            [InlineKeyboardButton("Отмена", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 <b>Персональный кулинарный помощник</b>\n\n"
            "Я помогу подобрать подходящие блюда и составить меню!\n\n"
            "Пожалуйста, укажите:\n"
            "• Ваши предпочтения в еде\n"
            "• Прием пищи (завтрак/обед/ужин)\n"
            "• Особые пожелания\n\n"
            "<i>Пример: Ищу идеи для легкого ужина, вегетарианское, быстрого приготовления</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return ConversationState.WAITING_FOR_ASSISTANT_RESPONSE
        
    except Exception as e:
        logger.error(f"Error in AI assistant command: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже."
        )
        return ConversationHandler.END

async def handle_assistant_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END

    user_id = update.effective_user.id
    try:
        user_message = update.message.text
        logger.info(f"Processing AI assistant request from user {user_id}: {user_message}")
        
        await update.message.reply_chat_action("typing")
        
        response = await get_advice_response(user_message)
        
        if not response:
            raise Exception("Failed to generate advice")

        keyboard = [
            [InlineKeyboardButton("Получить другой совет", callback_data="advice_again")],
            [InlineKeyboardButton("Найти рецепт", callback_data="search_recipe")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"👨‍🍳 <b>Мои рекомендации:</b>\n\n{escape(response)}",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        logger.info(f"AI assistant response sent to user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in AI assistant handler for user {user_id}: {e}")
        await update.message.reply_text(
            "❌ Извините, не удалось сформировать рекомендации.\n"
            "Пожалуйста, попробуйте описать ваши предпочтения более подробно."
        )
    
    return ConversationHandler.END

async def web_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /web_search command."""
    await update.message.reply_text(
        "🔍 <b>Поиск рецептов в интернете</b>\n\n"
        "Введите название блюда или ингредиенты для поиска рецепта:",
        parse_mode='HTML'
    )
    return ConversationState.WAITING_FOR_RECIPE_SEARCH

async def handle_recipe_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle recipe search query."""
    try:
        query = update.message.text
        await update.message.reply_text("🔍 Ищу рецепты, подождите...")

        parser = RecipeParser()
        recipes = parser.search_edamam(query)

        if not recipes:
            await update.message.reply_text(
                "К сожалению, рецептов по вашему запросу не найдено. "
                "Попробуйте изменить запрос или использовать другие ключевые слова."
            )
            return ConversationHandler.END

        # Получаем первый рецепт из списка
        first_recipe = recipes[0]
        recipe_details = (
            f"*Название*: {first_recipe['title']}\n"
            f"*Калории*: {first_recipe['calories']} ккал\n"
            f"*Ингредиенты*:\n" + "\n".join(f"- {ing}" for ing in first_recipe['ingredients'])
        )

        await update.message.reply_text(
            recipe_details,
            parse_mode='Markdown'
        )
        
        # Если есть еще рецепты, предложим их
        if len(recipes) > 1:
            other_recipes = "\n".join(
                f"{i+2}. {r['title']}"
                for i, r in enumerate(recipes[1:])
            )
            await update.message.reply_text(
                f"Найдены также другие рецепты:\n{other_recipes}\n\n"
                "Для поиска нового рецепта используйте команду /web_search"
            )

    except Exception as e:
        logger.error(f"Error in recipe search: {e}")
        await update.message.reply_text(
            "Произошла ошибка при поиске рецепта. Попробуйте позже."
        )
    
    return ConversationHandler.END

async def handle_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
   if not update.callback_query or not update.effective_user:
       return None
       
   query = update.callback_query
   user_id = update.effective_user.id
   
   try:
       await query.answer()
       logger.info(f"Processing callback query from user {user_id}: {query.data}")
       
       if not subscription_manager or not subscription_db:
           logger.error("Subscription systems not initialized")
           await query.edit_message_text("Сервис временно недоступен")
           return ConversationHandler.END
       
       if query.data == 'show_plans':
           current_users = subscription_db.get_total_users_count()
           prices = SUBSCRIPTION_PRICES_V1 if current_users <= TRIAL_USER_LIMIT else SUBSCRIPTION_PRICES_V2
           
           keyboard = [
               [InlineKeyboardButton("🎖 Standard", callback_data="tier_standard")],
               [InlineKeyboardButton("👑 Premium", callback_data="tier_premium")],
               [InlineKeyboardButton("❌ Закрыть", callback_data="close")]
           ]
           reply_markup = InlineKeyboardMarkup(keyboard)
           
           # Получаем информацию о текущей подписке пользователя
           subscription_info = subscription_db.get_user_subscription(user_id)
           is_trial = subscription_info.get('is_trial', False) if subscription_info else False
           days_left = subscription_info.get('days_left', 0) if subscription_info else 0
           
           message = "📋 <b>Доступные тарифы</b>\n\n"
           
           if is_trial:
               message += f"У вас активирован пробный период\nОсталось дней: <b>{days_left}</b>\n\n"
           
           message += (
               "🎖 <b>Standard</b>\n"
               "• Поиск рецептов из книги 1952 года\n"
               "• Расчет калорий\n"
               "• Базовые рекомендации\n"
               f"Цена: от {prices['standard'][1]} руб./мес\n\n"
               "👑 <b>Premium</b>\n"
               "• Все функции Standard\n"
               "• ИИ генерация рецептов\n"
               "• Персональный помощник\n"
               "• Неограниченный доступ\n"
               f"Цена: от {prices['premium'][1]} руб./мес\n\n"
               "<i>💫 Выберите тариф для продолжения</i>"
           )
           
           try:
               await query.edit_message_text(
                   text=message,
                   reply_markup=reply_markup,
                   parse_mode='HTML'
               )
               return ConversationStates.CHOOSING_TIER.value
           except TelegramError as e:
               if "message is not modified" not in str(e).lower():
                   logger.error(f"Error updating message: {e}")
                   # Если не можем отредактировать, отправляем новое сообщение
                   await query.message.reply_text(
                       text=message,
                       reply_markup=reply_markup,
                       parse_mode='HTML'
                   )
               return ConversationStates.CHOOSING_TIER.value
           
       elif query.data.startswith('tier_'):
           context.user_data['chosen_tier'] = query.data.split('_')[1]
           return await subscription_manager.handle_tier_choice(update, context)
           
       elif query.data.startswith('duration_'):
           if 'chosen_tier' not in context.user_data:
               await query.edit_message_text(
                   "Ошибка: не выбран тариф. Начните сначала.",
                   reply_markup=InlineKeyboardMarkup([[
                       InlineKeyboardButton("Начать сначала", callback_data="show_plans")
                   ]])
               )
               return ConversationHandler.END
           return await subscription_manager.handle_duration_choice(update, context)
           
       elif query.data == 'check_payment':
           if not context.user_data.get('payment_id'):
               await query.edit_message_text(
                   "Ошибка: платеж не найден. Начните сначала.",
                   reply_markup=InlineKeyboardMarkup([[
                       InlineKeyboardButton("Начать сначала", callback_data="show_plans")
                   ]])
               )
               return ConversationHandler.END
           return await subscription_manager.check_payment(update, context)
           
       elif query.data == 'cancel_payment':
           await query.edit_message_text(
               "❌ Оплата отменена.\n"
               "Используйте /manage для управления подпиской."
           )
           return ConversationHandler.END
           
       elif query.data == 'close':
           await query.delete_message()
           return ConversationHandler.END

       elif query.data == 'search_recipe':
           await recipes(update, context)
           return ConversationHandler.END

       elif query.data == 'calculate_calories':
           return ConversationHandler.END

       elif query.data == 'generate_again':
           await ai_recipes_command(update, context)
           return ConversationHandler.END

       elif query.data == 'advice_again':
           await ai_assistant_command(update, context)
           return ConversationHandler.END

       elif query.data == 'help':
           await help_command(update, context)
           return ConversationHandler.END
           
   except Exception as e:
       logger.error(f"Error in subscription callback handler: {e}")
       try:
           error_keyboard = [[InlineKeyboardButton("Попробовать снова", callback_data="show_plans")]]
           await query.edit_message_text(
               "Произошла ошибка. Попробуйте позже.",
               reply_markup=InlineKeyboardMarkup(error_keyboard)
           )
       except Exception:
           pass
       return ConversationHandler.END

def main() -> None:
    try:
        if not check_bot_instance():
            logger.critical("Another bot instance is running")
            sys.exit(1)

        signal.signal(signal.SIGTERM, lambda s, f: cleanup())
        signal.signal(signal.SIGINT, lambda s, f: cleanup())

        data_dir = Path("data").resolve()
        data_dir.mkdir(parents=True, exist_ok=True)

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("Missing Telegram bot token")

        global subscription_db, yookassa_payment, subscription_manager
        subscription_db, yookassa_payment, subscription_manager = initialize_systems()
        logger.info("All systems initialized successfully")

        persistence = PicklePersistence(filepath="conversation_states")
        application = ApplicationBuilder().token(token).persistence(persistence).build()
        application.add_error_handler(error_handler)

        basic_handlers = [
            CommandHandler("start", start),
            CommandHandler("help", help_command),
            CommandHandler("profile", handle_profile),
            CommandHandler("subscription", handle_subscription),
            CommandHandler("user_stats", user_stats)
        ]
        subscription_conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("manage", subscription_manager.handle_manage),
                CallbackQueryHandler(handle_subscription_callback, pattern='^show_plans$')
            ],
            states={
                ConversationStates.CHOOSING_TIER.value: [
                    CallbackQueryHandler(handle_subscription_callback, pattern='^tier_.*$')
                ],
                ConversationStates.CHOOSING_DURATION.value: [
                    CallbackQueryHandler(handle_subscription_callback, pattern='^duration_.*$')
                ],
                ConversationStates.CHECKING_PAYMENT.value: [
                    CallbackQueryHandler(handle_subscription_callback, pattern='^check_payment$'),
                    CallbackQueryHandler(handle_subscription_callback, pattern='^cancel_payment$')
                ]
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(cancel, pattern='^(cancel|close)$')
            ],
            allow_reentry=True,
            name='subscription_conversation',
            persistent=False,
            per_message=False,
            per_chat=False
        )
        
        recipe_handlers = [
            ConversationHandler(
                entry_points=[CommandHandler("recipes", recipes)],
                states={
                    ConversationState.WAITING_FOR_RECIPE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, search_by_name)
                    ],
                },
                fallbacks=[
                    CommandHandler("cancel", cancel),
                    CallbackQueryHandler(cancel, pattern='^cancel$')
                ],
                allow_reentry=True
            ),
            ConversationHandler(
                entry_points=[CommandHandler("ai_recipes", ai_recipes_command)],
                states={
                    ConversationState.AI_RECIPE: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_recipe)
                    ],
                },
                fallbacks=[
                    CommandHandler("cancel", cancel),
                    CallbackQueryHandler(cancel, pattern='^cancel$')
                ],
                allow_reentry=True
            ),
            ConversationHandler(
                entry_points=[CommandHandler("web_search", web_search_command)],
                states={
                    ConversationState.WAITING_FOR_RECIPE_SEARCH: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_recipe_search)
                    ],
                },
                fallbacks=[
                    CommandHandler("cancel", cancel),
                    CallbackQueryHandler(cancel, pattern='^cancel$')
                ],
                allow_reentry=True
            ),
        ]

        ai_assistant_handler = ConversationHandler(
            entry_points=[CommandHandler("ai_assistant", ai_assistant_command)],
            states={
                ConversationState.WAITING_FOR_ASSISTANT_RESPONSE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_assistant_response)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(cancel, pattern='^cancel$')
            ],
            allow_reentry=True
        )

        for handler in basic_handlers:
            application.add_handler(handler)

        application.add_handler(subscription_conv_handler)

        for handler in recipe_handlers:
            application.add_handler(handler)

        application.add_handler(ai_assistant_handler)

        calories_handler = ConversationHandler(
            entry_points=[CommandHandler("calories", handle_calories)],
            states={
                ConversationState.WAITING_FOR_CALORIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calculate_and_reply)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern='^cancel$')
        ],
        allow_reentry=True
    )

        application.add_handler(calories_handler)

        application.add_handler(
            MessageHandler(
                filters.Regex(r"/webhook/payment") & filters.ChatType.PRIVATE,
                yookassa_payment.handle_notification
            )
        )

        application.add_handler(
            CallbackQueryHandler(handle_subscription_callback),
            group=1
        )

        logger.info("Bot initialization completed successfully")
        try:
            logger.info("Starting bot polling...")
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=False
            )
        except Conflict:
            logger.critical("Bot is already running in another process")
            cleanup()
            sys.exit(1)
        except Exception as e:
            logger.critical(f"Failed to start polling: {e}")
            cleanup()
            raise

    except Exception as e:
        logger.critical(f"Critical error during bot initialization: {e}")
        cleanup()
        raise SystemExit(f"Bot initialization failed: {e}")

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(main())
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        cleanup()
    except SystemExit as e:
        logger.critical(f"Bot stopped: {e}")
        cleanup()
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Unexpected error: {e}")
        cleanup()
        sys.exit(1)