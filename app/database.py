import os
import psycopg2
from psycopg2 import pool
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# === Конфигурация подключения ===
# Параметры подключения берутся из переменных окружения или используются значения по умолчанию
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASS", ""),
}

# Проверка: в production пароль не должен быть пустым
if not os.getenv("DB_PASS") and os.getenv("ENVIRONMENT") == "production":
    raise RuntimeError("В production режиме пароль базы данных должен быть установлен через переменную окружения DB_PASS!")

SCHEMA_NAME = "maxxx-local"

# === Пул соединений ===
# Глобальный пул соединений для производительности
db_pool: Optional[pool.ThreadedConnectionPool] = None

def init_db_pool(minconn: int = 2, maxconn: int = 10):
    """
    Инициализирует пул соединений с базой данных.
    
    Args:
        minconn: Минимальное количество соединений в пуле
        maxconn: Максимальное количество соединений в пуле
    """
    global db_pool
    try:
        db_pool = pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            **DB_CONFIG
        )
        logger.info(f"Пул соединений к БД инициализирован (min={minconn}, max={maxconn})")
    except Exception as e:
        logger.error(f"Ошибка инициализации пула соединений: {e}")
        raise

def get_db_connection():
    """
    Получает соединение из пула или создаёт новое (если пул не инициализирован).
    Автоматически устанавливает search_path на схему "maxxx-local".
    
    Returns:
        psycopg2.connection: активное соединение с БД
    
    Raises:
        RuntimeError: если не удаётся получить соединение с базой данных
    """
    if db_pool is not None:
        try:
            conn = db_pool.getconn()
            with conn.cursor() as cur:
                cur.execute('SET search_path TO %s' % psycopg2.extensions.quoted_identifier(SCHEMA_NAME))
            return conn
        except Exception as e:
            logger.error(f"Ошибка получения соединения из пула: {e}")
            raise RuntimeError(f"Не удалось получить соединение из пула: {e}") from e
    else:
        # Fallback: создаём новое соединение (для тестов или если пул не инициализирован)
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            with conn.cursor() as cur:
                cur.execute('SET search_path TO %s' % psycopg2.extensions.quoted_identifier(SCHEMA_NAME))
            return conn
        except Exception as e:
            raise RuntimeError(f"Не удалось подключиться к базе данных: {e}") from e

def release_db_connection(conn):
    """
    Возвращает соединение обратно в пул.
    
    Args:
        conn: Соединение для возврата
    """
    global db_pool
    if db_pool is not None:
        try:
            db_pool.putconn(conn)
        except Exception as e:
            logger.error(f"Ошибка возврата соединения в пул: {e}")
    else:
        conn.close()