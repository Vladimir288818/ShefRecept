import logging
from openai import AsyncOpenAI
import os
from typing import Optional

# Инициализация логгера
logger = logging.getLogger(__name__)

# Инициализация клиента OpenAI
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def calculate_calories(ingredients: str) -> Optional[str]:
    # Шаблон запроса для ИИ с акцентом на краткость ответа и без анализа каждого ингредиента
    calorie_prompt = (
        f"Используя следующий список ингредиентов:\n\n{ingredients}\n\n"
        "Рассчитай общую калорийность и состав по белкам, жирам и углеводам для всего блюда. "
        "Не анализируй ингредиенты по отдельности. Предоставь только итоговые данные в формате:\n\n"
        "### Калорийность: [значение]\n"
        "### Белки: [значение]\n"
        "### Жиры: [значение]\n"
        "### Углеводы: [значение]\n\n"
        "Не показывай расчет для каждого ингредиента. Только общий результат для блюда. Дай короткие пояснения"
    )
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты эксперт по кулинарии и питанию. Ответь строго по формату."},
                {"role": "user", "content": calorie_prompt}
            ],
            max_tokens=200,  # Ограничение для краткости ответа
            temperature=0.5
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка OpenAI API при расчете калорийности: {e}")
        return None