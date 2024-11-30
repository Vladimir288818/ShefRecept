#handlers.py
from telegram import Update
from telegram.ext import ContextTypes
from .database import search_recipe_by_name

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Ответ на команду /start
    await update.message.reply_text(
        "Привет! Я кулинарный бот-ассистент. Используйте /menu для начала работы."
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Ответ на команду /menu
    await update.message.reply_text(
        "Выберите категорию:\n1. Поиск рецептов\n2. Подписка\n3. Помощь"
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Логика поиска рецепта
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Пожалуйста, укажите название рецепта.")
        return

    # Здесь выполняется поиск рецепта в базе данных
    recipes = search_recipe_by_name(query)
    if recipes:
        response = "\n\n".join([f"Название: {r[0]}\nОписание: {r[1]}" for r in recipes])
    else:
        response = "Рецепт не найден."

    await update.message.reply_text(response)