import os
import logging
from openai import AsyncOpenAI
from telegram.ext import CommandHandler, MessageHandler, filters
from typing import Optional

# Инициализация логгера
logger = logging.getLogger(__name__)

# Инициализация клиента OpenAI
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def get_openai_response(prompt: str) -> Optional[str]:
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты дружелюбный и веселый эксперт по здоровому питанию и кулинарии."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка OpenAI API: {e}")
        return None

async def get_recipe_with_calories(prompt: str) -> Optional[str]:
    calorie_prompt = (
        f"{prompt} Ты профессиональный повар, знающий кухню всего мира! Ты специализируешься на создании рецептов. Пользователь запрашивает рецепт, который соответствует его запросу (например, ингредиенты, тип приема пищи или особые предпочтения, такие как низкокалорийное или веганское блюдо). Ответ должен быть полным, с четким описанием ингредиентов, их количеством и пошаговыми инструкциями. Начинай ответ с названия блюда. Если пользователь не указал предпочтений, предложи универсальный рецепт. Не добавляй советы или рекомендации, только сам рецепт. "
        "Например:\n\n"
        "Ингредиенты:\n"
        "- Куриное филе, 200 г\n"
        "- Рис, 100 г\n"
        "- Оливковое масло, 1 ст. л.\n\n"
        "Калорийность:\n"
        "- Общее количество калорий: 500 ккал\n"
        "- Белки: 30 г, Жиры: 10 г, Углеводы: 50 г\n"
        "Представь информацию в подобном формате для каждого рецепта."
    )
    return await get_openai_response(calorie_prompt)

async def categories(update, context):
    await update.message.reply_text("Категории рецептов: Завтрак, Обед, Ужин.")

async def handle_text(update, context):
    user_message = update.message.text
    prompt = f"Предложи рецепт, связанный с '{user_message}', и укажи его калорийность."
    response = await get_recipe_with_calories(prompt)
    await update.message.reply_text(response if response else "Не смог найти рецепт.")

def init_ai(application):
    """Инициализация AI-модуля"""
    application.add_handler(CommandHandler("categories", categories))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("ИИ-модуль инициализирован.")