import os
import logging
from openai import AsyncOpenAI
from telegram.ext import CommandHandler, MessageHandler, filters
from typing import Optional

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AIAssistantError(Exception):
    """Базовый класс для ошибок AI-ассистента"""
    pass

class AIAssistant:
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация AI-ассистента
        
        Args:
            api_key (Optional[str]): API ключ OpenAI. Если не указан, берется из переменной окружения
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise AIAssistantError("OpenAI API key not found")
        
        self.client = AsyncOpenAI(api_key=self.api_key)
        logger.info("AI Assistant initialized successfully")

    async def get_advice_response(self, prompt: str) -> Optional[str]:
        """
        Получение совета по выбору блюд
   
        Args:
            prompt: Запрос пользователя
       
        Returns:
            Optional[str]: Ответ AI-ассистента или None в случае ошибки
        """
        try:
            system_prompt = """Ты кулинарный советник и даешь только советы! 
            Пользователь запрашивает рекомендации блюд с учетом предпочтений (например, веганское, диетическое, мясное). 
            Ответ должен быть кратким, с несколькими предложениями на выбор для каждого приема пищи, 
            подходящими для указанного времени дня. Для обеда предложи несколько вариантов супов, 
            основных блюд с гарниром и напитков. Включай конкретные названия блюд, если они подходят для быстрого поиска.
            В конце каждого ответа добавь фразу: 'Чтобы получить рецепт выбранного блюда, воспользуйтесь 
            командами /recipes или /ai_recipes.'"""

            completion = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.7
            )
       
            response = completion.choices[0].message.content
            logger.info("Successfully generated advice response")
            return response
       
        except Exception as e:
            logger.error(f"Error generating advice: {e}")
            return None

    async def handle_categories(self, update, context):
        """
        Обработчик для запроса категорий
        """
        message = """Категории советов: 
        🌅 Завтрак
        🌞 Обед
        🌙 Ужин
        
        Пожалуйста, уточните свои предпочтения, например:
        • веганское
        • диетическое
        • мясное меню
        """
        await update.message.reply_text(message)
        logger.info("Sent categories information")

    async def handle_text(self, update, context):
        """
        Обработчик текстовых сообщений для советов
        """
        user_message = update.message.text
        prompt = f"Подбери несколько вариантов блюд для '{user_message}'."
        
        response = await self.get_advice_response(prompt)
        
        if not response:
            error_message = "Не удалось найти подходящие варианты. Пожалуйста, попробуйте еще раз."
            await update.message.reply_text(error_message)
            logger.warning(f"Failed to generate response for prompt: {prompt}")
            return

        await update.message.reply_text(response)
        logger.info(f"Successfully processed user message: {user_message}")

def init_ai_assistant(application):
    """
    Инициализация AI-советника в приложении
    
    Args:
        application: Telegram application instance
    """
    try:
        ai_assistant = AIAssistant()
        application.add_handler(CommandHandler("categories", ai_assistant.handle_categories))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            ai_assistant.handle_text
        ))
        logger.info("AI Assistant module initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize AI Assistant: {e}")
        raise AIAssistantError(f"AI Assistant initialization failed: {e}")