import os
import psycopg2
from fuzzywuzzy import process
from urllib.parse import urlparse # Добавим для парсинга URL

def create_connection():
    try:
        # Получаем DATABASE_URL
        DATABASE_URL = os.environ.get("DATABASE_URL")
        
        if DATABASE_URL is None:
            raise ValueError("DATABASE_URL не установлена в переменных окружения")
            
        # Исправление формата URL для Heroku
        # Heroku иногда использует 'postgres://', а psycopg2 требует 'postgresql://'
        if DATABASE_URL.startswith('postgres://'):
            DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
            
        # Добавим вывод для отладки (потом можно убрать)
        print("Подключаемся к базе данных...")
        
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        print("Успешное подключение к базе данных")
        return conn
        
    except Exception as e:
        print(f"Ошибка при подключении к базе данных: {str(e)}")
        return None

def create_tables():
    """Создание таблиц, если они не существуют"""
    conn = create_connection()
    if conn is None:
        return
    
    try:
        cursor = conn.cursor()
        
        # Создаем таблицу рецептов, если она не существует
        create_table_query = """
        CREATE TABLE IF NOT EXISTS recipes (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            ingredients TEXT NOT NULL,
            instructions TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        cursor.execute(create_table_query)
        conn.commit()
        print("Таблицы успешно созданы/проверены")
        
    except Exception as e:
        print(f"Ошибка при создании таблиц: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def get_all_recipe_names():
    conn = create_connection()
    
    if conn is None:
        return []
    
    cursor = conn.cursor()
    
    try:
        query = "SELECT name FROM recipes"
        cursor.execute(query)
        names = [name[0] for name in cursor.fetchall()]
        return names
        
    except psycopg2.Error as e:
        print(f"Ошибка при получении названий рецептов: {str(e)}")
        return []
    finally:
        cursor.close()
        conn.close()

def fuzzy_search_recipe_by_name(recipe_name):
    all_names = get_all_recipe_names()
    
    if not all_names:
        print("База рецептов пуста")
        return None
    
    closest_match = process.extractOne(recipe_name, all_names)
    
    if closest_match and closest_match[1] >= 70:
        return closest_match[0]
    return None

def get_recipe_by_name(recipe_name):
    conn = create_connection()
    
    if conn is None:
        return None
    
    cursor = conn.cursor()
    
    try:
        query = """
        SELECT name, ingredients, instructions 
        FROM recipes 
        WHERE name = %s
        """
        cursor.execute(query, (recipe_name,))
        recipe = cursor.fetchone()
        return recipe
        
    except psycopg2.Error as e:
        print(f"Ошибка при получении рецепта: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()