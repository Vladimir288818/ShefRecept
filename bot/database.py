import sqlite3
from fuzzywuzzy import process

# Подключение к существующей базе данных SQLite
def create_connection():
    try:
        conn = sqlite3.connect('C:/Users/WIN10/Desktop/culinary_bot/recipes.db')  # Путь к базе данных
        return conn
    except sqlite3.Error as e:
        print(f"Ошибка при подключении к базе данных: {e}")
        return None

# Получение всех названий рецептов для нечеткого поиска
def get_all_recipe_names():
    conn = create_connection()
    
    if conn is None:
        return []
    
    cursor = conn.cursor()
    
    try:
        # Получение всех названий рецептов
        query = "SELECT name FROM recipes"
        cursor.execute(query)
        names = cursor.fetchall()
        names = [name[0] for name in names]  # Извлекаем только названия
    except sqlite3.Error as e:
        print(f"Ошибка при выполнении запроса: {e}")
        names = []
    finally:
        cursor.close()
        conn.close()

    return names

# Нечеткий поиск рецепта по названию
def fuzzy_search_recipe_by_name(recipe_name):
    all_names = get_all_recipe_names()
    
    if not all_names:
        return None
    
    # Нечеткий поиск для нахождения наиболее похожего названия
    closest_match = process.extractOne(recipe_name, all_names)
    
    if closest_match[1] < 70:  # Если совпадение меньше 70%, считаем, что рецепт не найден
        return None
    
    # Если найдено совпадение, возвращаем полное название рецепта
    return closest_match[0]

# Поиск рецепта по точному названию (для получения полного рецепта)
def get_recipe_by_name(recipe_name):
    conn = create_connection()
    
    if conn is None:
        return None
    
    cursor = conn.cursor()
    
    try:
        # Получение рецепта по точному названию
        query = "SELECT name, ingredients, instructions FROM recipes WHERE name = ?"
        cursor.execute(query, (recipe_name,))
        recipe = cursor.fetchone()
    except sqlite3.Error as e:
        print(f"Ошибка при выполнении запроса: {e}")
        recipe = None
    finally:
        cursor.close()
        conn.close()

    return recipe