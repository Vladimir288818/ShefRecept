import os
import logging
from openai import AsyncOpenAI
from telegram.ext import CommandHandler, MessageHandler, filters
from typing import Optional

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация клиента OpenAI
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def get_openai_response(prompt: str) -> Optional[str]:
    """
    Получение ответа от OpenAI API
    
    Args:
        prompt: Запрос пользователя
        
    Returns:
        Optional[str]: Ответ от API или None в случае ошибки
    """
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
        logger.info("Successfully received OpenAI response")
        return completion.choices[0].message.content

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return None

async def get_recipe_with_calories(prompt: str) -> Optional[str]:
    """
    Получение рецепта с информацией о калориях
    
    Args:
        prompt: Запрос пользователя

    Returns:
        Optional[str]: Рецепт с калориями или None в случае ошибки
    """
    system_message = """Ты профессиональный повар, знающий кухню всего мира! 
    Ты специализируешься на создании рецептов. Пользователь запрашивает рецепт, 
    который соответствует его запросу (например, ингредиенты, тип приема пищи или 
    особые предпочтения, такие как низкокалорийное или веганское блюдо). 
    
    Ответ должен быть полным, с четким описанием ингредиентов, их количеством и 
    пошаговыми инструкциями. Начинай ответ с названия блюда. Если пользователь 
    не указал предпочтений, предложи универсальный рецепт. 
    
    Не добавляй советы или рекомендации, только сам рецепт.
    
    Формат ответа:
    
    Название блюда
    
    Ингредиенты:
    - Ингредиент 1, количество
    - Ингредиент 2, количество
    
    Калорийность:
    - Общее количество калорий: XXX ккал
    - Белки: XX г
    - Жиры: XX г
    - Углеводы: XX г
    
    Способ приготовления:
    1. Шаг 1
    2. Шаг 2
    ..."""

    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Error generating recipe: {e}")
        return None

async def categories(update, context):
    """Обработчик команды /categories"""
    categories_message = """
    🍳 Категории рецептов:
    
    🌅 Завтрак
    • Каши и хлопья
    • Яичные блюда
    • Бутерброды и сэндвичи
    
    🌞 Обед
    • Супы
    • Основные блюда
    • Гарниры
    
    🌙 Ужин
    • Легкие блюда
    • Салаты
    • Запеканки
    
    Выберите категорию и отправьте свой запрос!
    """
    await update.message.reply_text(categories_message)
    logger.info("Sent categories information")

async def handle_text(update, context):
    """Обработчик текстовых сообщений"""
    user_message = update.message.text
    prompt = f"Предложи рецепт, связанный с '{user_message}', и укажи его калорийность."
    
    response = await get_recipe_with_calories(prompt)
    
    if not response:
        await update.message.reply_text(
            "Не удалось найти подходящие варианты. Пожалуйста, попробуйте еще раз."
        )
        return
        
    await update.message.reply_text(response)

def init_ai_assistant(application):
    """Инициализация AI-советника"""
    application.add_handler(CommandHandler("categories", categories))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Модуль AI-советника инициализирован.")