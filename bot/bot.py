import os
import logging
from typing import Optional
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    ConversationHandler, 
    filters, 
    ContextTypes,
)
from dotenv import load_dotenv
from bot.database import fuzzy_search_recipe_by_name, get_recipe_by_name
from bot.ai_module import get_openai_response
from bot.web_search import RecipeParser
from bot.user_activity import log_user_interaction, get_users_count, create_users_table
from bot.calories import calculate_calories
from bot.sub_mgr import SubscriptionManager
from bot.sub_db import SubscriptionDB
from bot.ai_assistant import get_advice_response
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_RECIPE = 0
AI_RECIPE = 1
WAITING_FOR_RECIPE_SEARCH = 2
WAITING_FOR_CALORIES = 3
WAITING_FOR_ASSISTANT_RESPONSE = 4

# Инициализация менеджера подписок
DB_PATH = "subscriptions.db"
subscription_db = SubscriptionDB(DB_PATH)
subscription_manager = SubscriptionManager(subscription_db)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    try:
        user_id = update.effective_user.id
        log_user_interaction(user_id)
        await update.message.reply_text(
            "Добро пожаловать! Используйте Меню для получения списка команд."
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
    commands = [
        "/start - Начало работы с ботом",
        "/help - Помощь и справка",
        "/profile - Просмотр статуса подписки",
        "/manage - Управление подпиской",
        "/subscription - Проверка доступа",
        "/recipes - Поиск рецептов по названию",
        "/ai_recipes - Генерация рецептов с помощью ИИ",
        "/web_search - Поиск рецептов на сайтах",
        "/user_stats - Статистика пользователей",
        "/search - Начать новый поиск рецепта",
        "/calories - Рассчитать калорийность блюда",
        "/ai_assistant - Совет по выбору блюда или меню"
    ]
    await update.message.reply_text("\n".join(commands))

"""Обработчик команды /profile."""
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /profile, отправляет изображение с информацией о подписке."""
    try:
        # Отправка изображения с информацией о подписке
        with open("assets/sub_info.png", "rb") as image_file:
            await update.message.reply_photo(
                photo=image_file,
                caption="Информация о подписках. Ознакомьтесь с возможностями каждого плана."
            )
    except FileNotFoundError:
        await update.message.reply_text("Изображение с информацией о подписках не найдено.")
    except Exception as e:
        logger.error(f"Error in profile command: {e}")
        await update.message.reply_text("Произошла ошибка при загрузке информации. Попробуйте позже.")

async def manage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /manage."""
    user_id = update.effective_user.id
    response = await subscription_manager.handle_manage(update, context)
    await update.message.reply_text(response)

async def subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /subscription."""
    user_id = update.effective_user.id
    response = await subscription_manager.handle_subscription(update, context)
    await update.message.reply_text(response)

async def recipes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /recipes command."""
    await update.message.reply_text("Введите название рецепта для поиска:")
    return WAITING_FOR_RECIPE

async def search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle recipe search by name."""
    try:
        recipe_name = update.message.text
        logger.info(f"Searching recipe: {recipe_name}")

        closest_recipe_name = fuzzy_search_recipe_by_name(recipe_name)
        if not closest_recipe_name:
            await update.message.reply_text("Рецепт не найден.")
            return ConversationHandler.END

        recipe = get_recipe_by_name(closest_recipe_name)
        if not recipe:
            await update.message.reply_text("Ошибка при получении рецепта.")
            return ConversationHandler.END

        message = (
            f"Название: {recipe[0]}\n"
            f"Ингредиенты: {recipe[1]}\n"
            f"Инструкции: {recipe[2]}"
        )
        await update.message.reply_text(message)
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in recipe search: {e}")
        await update.message.reply_text("Произошла ошибка при поиске рецепта.")
        return ConversationHandler.END

async def ai_recipes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /ai_recipes command."""
    await update.message.reply_text(
        "Пожалуйста, введите запрос для генерации рецепта или укажите ингредиенты:"
    )
    return AI_RECIPE

async def handle_ai_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle AI recipe generation."""
    try:
        user_message = update.message.text
        prompt = f"Предложи рецепт на основе запроса: {user_message}"

        recipe = await get_openai_response(prompt)
        if recipe:
            await update.message.reply_text(recipe)
        else:
            await update.message.reply_text(
                "Извините, произошла ошибка при генерации рецепта. Попробуйте позже."
            )
    except Exception as e:
        logger.error(f"Error in AI recipe generation: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
    
    return ConversationHandler.END

async def web_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /web_search command."""
    await update.message.reply_text(
        "Введите название блюда или ингредиенты, из которых вы планируете приготовить блюдо:"
    )
    return WAITING_FOR_RECIPE_SEARCH

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

async def handle_calories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /calories command."""
    await update.message.reply_text("Вставьте скопированный текст рецепта или введите список ингредиентов с количеством для расчета калорийности:")
    return WAITING_FOR_CALORIES

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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle conversation cancellation."""
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /user_stats command."""
    try:
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
        user_count = get_users_count(start_date, end_date)
        await update.message.reply_text(
            f"Количество уникальных пользователей за последние 30 дней: {user_count}"
        )
    except Exception as e:
        logger.error(f"Error in user stats: {e}")
        await update.message.reply_text("Ошибка при получении статистики.")

# Обработчик команды /ai_assistant
async def ai_assistant_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /ai_assistant command for menu recommendations."""
    await update.message.reply_text(
        "🍽 Помогу подобрать подходящие блюда и составить меню!\n\n"
        "Пожалуйста, укажите:\n"
        "- Ваши предпочтения в еде (например, вегетарианская, безглютеновая)\n"
        "- Прием пищи (завтрак/обед/ужин)\n"
        "- Особые пожелания (быстрое приготовление, диетическое и т.д.)\n\n"
        "Пример: 'Ищу идеи для легкого ужина, вегетарианское, быстрого приготовления'"
    )
    return WAITING_FOR_ASSISTANT_RESPONSE

async def handle_assistant_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text input for ai_assistant recommendations."""
    try:
        user_message = update.message.text
        response = await get_advice_response(user_message)
        
        if response:
            await update.message.reply_text(response)
        else:
            await update.message.reply_text(
                "Извините, не удалось сформировать рекомендации. "
                "Пожалуйста, попробуйте описать ваши предпочтения более подробно."
            )
            
    except Exception as e:
        logger.error(f"Error in AI assistant handler: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке запроса. "
            "Пожалуйста, попробуйте позже."
        )
    
    return ConversationHandler.END

def main() -> None:
    """Main function to run the bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Missing Telegram bot token")
    
    try:
        create_users_table()
        application = ApplicationBuilder().token(token).build()

        # Basic command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("profile", profile_command))
        application.add_handler(CommandHandler("manage", manage_command))
        application.add_handler(CommandHandler("subscription", subscription_command))
        application.add_handler(CommandHandler("user_stats", user_stats))

        # Recipe search conversation handler
        recipe_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("recipes", recipes)],
            states={
                WAITING_FOR_RECIPE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        search_by_name
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
        application.add_handler(recipe_conv_handler)

        # AI recipe conversation handler
        ai_recipes_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("ai_recipes", ai_recipes_command)],
            states={
                AI_RECIPE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        handle_ai_recipe
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
        application.add_handler(ai_recipes_conv_handler)

        # Web search conversation handler
        web_search_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("web_search", web_search_command)],
            states={
                WAITING_FOR_RECIPE_SEARCH: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        handle_recipe_search
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
        application.add_handler(web_search_conv_handler)

        # Calories calculation conversation handler
        calories_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("calories", handle_calories)],
            states={
                WAITING_FOR_CALORIES: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        calculate_and_reply
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
        application.add_handler(calories_conv_handler)

        # AI Assistant conversation handler
        assistant_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("ai_assistant", ai_assistant_command)],
            states={
                WAITING_FOR_ASSISTANT_RESPONSE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        handle_assistant_response
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
        application.add_handler(assistant_conv_handler)

        logger.info("Bot started")
        application.run_polling()

    except Exception as e:
        logger.error(f"Critical error: {e}")
        raise

if __name__ == "__main__":
    main()