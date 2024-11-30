import sqlite3
import logging
from typing import Optional, List, Tuple
from pathlib import Path
from fuzzywuzzy import process

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Базовый класс для ошибок базы данных"""
    pass

class Database:
    def __init__(self, db_path: str = 'recipes.db'):
        """
        Инициализация подключения к базе данных
        
        Args:
            db_path (str): Путь к файлу базы данных
        """
        self.db_path = Path(db_path).resolve()
        # Создание директории для базы данных
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Инициализация таблицы при первом создании
        self.initialize_database()

    def initialize_database(self) -> None:
        """
        Инициализация базы данных и создание необходимых таблиц
        """
        try:
            with self.create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS recipes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        ingredients TEXT NOT NULL,
                        instructions TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("Database initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            raise DatabaseError(f"Failed to initialize database: {e}")

    def create_connection(self) -> sqlite3.Connection:
        """
        Создание подключения к базе данных
        
        Returns:
            sqlite3.Connection: Объект подключения к базе данных
            
        Raises:
            DatabaseError: При ошибке подключения к базе данных
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Использование Row factory для удобного доступа к колонкам
            return conn
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise DatabaseError(f"Failed to connect to database: {e}")

    def get_all_recipe_names(self) -> List[str]:
        """
        Получение всех названий рецептов
        
        Returns:
            List[str]: Список названий рецептов
        """
        try:
            with self.create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM recipes")
                return [row['name'] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error fetching recipe names: {e}")
            return []

    def fuzzy_search_recipe_by_name(self, recipe_name: str, min_similarity: int = 70) -> Optional[str]:
        """
        Нечеткий поиск рецепта по названию
        
        Args:
            recipe_name (str): Искомое название рецепта
            min_similarity (int): Минимальный процент совпадения (по умолчанию 70)
            
        Returns:
            Optional[str]: Найденное название рецепта или None
        """
        all_names = self.get_all_recipe_names()
        
        if not all_names:
            return None
        
        # Нечеткий поиск для нахождения наиболее похожего названия
        closest_match = process.extractOne(recipe_name, all_names)
        
        if closest_match[1] < min_similarity:
            logger.info(f"No close matches found for recipe: {recipe_name}")
            return None
        
        logger.info(f"Found match for '{recipe_name}': '{closest_match[0]}' with similarity {closest_match[1]}%")
        return closest_match[0]

    def get_recipe_by_name(self, recipe_name: str) -> Optional[Tuple[str, str, str]]:
        """
        Поиск рецепта по точному названию
        
        Args:
            recipe_name (str): Точное название рецепта
            
        Returns:
            Optional[Tuple[str, str, str]]: Кортеж (название, ингредиенты, инструкции) или None
        """
        try:
            with self.create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name, ingredients, instructions FROM recipes WHERE name = ?",
                    (recipe_name,)
                )
                row = cursor.fetchone()
                
                if row:
                    return (row['name'], row['ingredients'], row['instructions'])
                logger.info(f"Recipe not found: {recipe_name}")
                return None
            
        except sqlite3.Error as e:
            logger.error(f"Error fetching recipe: {e}")
            return None

    def add_recipe(self, name: str, ingredients: str, instructions: str) -> bool:
        """
        Добавление нового рецепта в базу данных
        
        Args:
            name (str): Название рецепта
            ingredients (str): Список ингредиентов
            instructions (str): Инструкции по приготовлению
            
        Returns:
            bool: True если рецепт успешно добавлен, False в противном случае
        """
        try:
            with self.create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO recipes (name, ingredients, instructions) VALUES (?, ?, ?)",
                    (name, ingredients, instructions)
                )
                conn.commit()
                logger.info(f"Recipe '{name}' added successfully")
                return True
        except sqlite3.IntegrityError:
            logger.warning(f"Recipe '{name}' already exists")
            return False
        except sqlite3.Error as e:
            logger.error(f"Error adding recipe: {e}")
            return False