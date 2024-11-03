import requests
from typing import List, Dict
import logging
import os
import re
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

load_dotenv()

logger = logging.getLogger(__name__)

class RecipeParser:
    
    EDAMAM_BASE_URL = "https://api.edamam.com/api/recipes/v2"
    
    def __init__(self):
        self.session = requests.Session()
        self.edamam_app_id = os.getenv("EDAMAM_APP_ID")
        self.edamam_api_key = os.getenv("EDAMAM_API_KEY")

        # Проверка на наличие API ключей
        if not self.edamam_app_id or not self.edamam_api_key:
            logger.error("EDAMAM_APP_ID или EDAMAM_API_KEY отсутствуют в .env файле")
            raise ValueError("Отсутствуют EDAMAM_APP_ID или EDAMAM_API_KEY")

    def convert_units(self, ingredient: str) -> str:
        """Convert imperial units in the ingredient text to metric."""
        ingredient = re.sub(r"(\d+(?:\.\d+)?)\s*oz\b", lambda x: f"{float(x.group(1)) * 28.3495:.1f} г", ingredient)
        ingredient = re.sub(r"(\d+(?:\.\d+)?)\s*lb\b", lambda x: f"{float(x.group(1)) * 453.592:.1f} г", ingredient)
        ingredient = re.sub(r"(\d+(?:\.\d+)?)\s*cups?\b", lambda x: f"{float(x.group(1)) * 240:.1f} мл", ingredient)
        ingredient = re.sub(r"(\d+(?:\.\d+)?)\s*tbsp\b", lambda x: f"{float(x.group(1)) * 15:.1f} мл", ingredient)
        ingredient = re.sub(r"(\d+(?:\.\d+)?)\s*tsp\b", lambda x: f"{float(x.group(1)) * 5:.1f} мл", ingredient)
        return ingredient

    def search_edamam(self, query: str) -> List[Dict[str, str]]:
        try:
            translated_query = GoogleTranslator(source='auto', target='en').translate(query)
            logger.info(f"Переведенный запрос: {translated_query}")
            
            params = {
                'type': 'public',
                'q': translated_query,
                'app_id': self.edamam_app_id,
                'app_key': self.edamam_api_key
            }
            
            response = self.session.get(self.EDAMAM_BASE_URL, params=params)
            
            logger.info(f"Код ответа от Edamam: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"Ошибка при обращении к API Edamam: {response.status_code}")
                return []

            data = response.json()
            
            if 'hits' not in data or not data['hits']:
                logger.warning("Рецепты не найдены для запроса: " + query)
                return []

            recipes = []
            for hit in data['hits'][:5]:
                recipe = hit['recipe']

                title_ru = GoogleTranslator(source='en', target='ru').translate(recipe['label'])
                ingredients_ru = [
                    self.convert_units(GoogleTranslator(source='en', target='ru').translate(ing))
                    for ing in recipe['ingredientLines']
                ]
                
                recipes.append({
                    'title': title_ru,
                    'url': recipe['url'],  # URL для полного рецепта с инструкцией
                    'image': recipe['image'],
                    'ingredients': ingredients_ru,
                    'calories': int(recipe['calories']),
                    'nutrients': {
                        'protein': int(recipe['totalNutrients']['PROCNT']['quantity']),
                        'fat': int(recipe['totalNutrients']['FAT']['quantity']),
                        'carbs': int(recipe['totalNutrients']['CHOCDF']['quantity'])
                    }
                })
            
            return recipes

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при обращении к API Edamam: {e}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка при поиске рецептов: {e}")
            return []