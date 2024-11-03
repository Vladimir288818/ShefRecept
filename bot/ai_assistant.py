import os
import logging
from openai import AsyncOpenAI
from telegram.ext import CommandHandler, MessageHandler, filters
from typing import Optional

# Инициализация логгера
logger = logging.getLogger(__name__)

# Инициализация клиента OpenAI
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Функция для получения совета по выбору блюд
async def get_advice_response(prompt: str) -> Optional[str]:
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты кулинарный советник и даешь только советы! Пользователь запрашивает рекомендации блюд с учетом предпочтений (например, веганское, диетическое, мясное). Ответ должен быть кратким, с несколькими предложениями на выбор для каждого приема пищи, подходящими для указанного времени дня. Для обеда предложи несколько вариантов супов, основных блюд с гарниром и напитков. Включай конкретные названия блюд, если они подходят для быстрого поиска. В конце каждого ответа добавь фразу: 'Чтобы получить рецепт выбранного блюда, воспользуйтесь командами /recipes или /ai_recipes.' Пример ответа: 'Завтрак: овсянка с ягодами, омлет с овощами или творожная запеканка. Обед: суп щи, борщ или овощной суп; для второго блюда — куриные котлеты с гречкой, говяжий стейк с картофелем или тушеные овощи; напиток — компот, морс или чай.'"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка OpenAI API: {e}")
        return None

# Обработчик для запроса категорий
async def categories(update, context):
    await update.message.reply_text("Категории советов: Завтрак, Обед, Ужин. Пожалуйста, уточните свои предпочтения, например, веганское, диетическое, или мясное меню.")

# Обработчик текстовых сообщений для советов
async def handle_text(update, context):
    user_message = update.message.text
    prompt = f"Подбери несколько вариантов блюд для '{user_message}'."
    response = await get_advice_response(prompt)
    await update.message.reply_text(response if response else "Не удалось найти подходящие варианты. Пожалуйста, попробуйте еще раз.")

# Инициализация AI-советника
def init_ai_assistant(application):
    """Инициализация AI-советника"""
    application.add_handler(CommandHandler("categories", categories))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Модуль AI-советника инициализирован.")