"""
Модуль подключения к базе данных PostgreSQL.

Функции модуля:
- Создание соединений с PostgreSQL
- Автоматическая установка search_path на схему "maxxx-local"
- Конфигурация подключения через переменные окружения

Примечание: Для production рекомендуется использовать pool соединений.
"""

import os
import psycopg2
from psycopg2 import pool
from typing import Optional

# === Конфигурация подключения ===
# Параметры подключения берутся из переменных окружения или используются значения по умолчанию
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASS", ""),
}

SCHEMA_NAME = "maxxx-local"


def get_db_connection():
    """
    Создаёт новое подключение к PostgreSQL и устанавливает search_path.
    
    Каждое соединение автоматически переключается на схему "maxxx-local",
    чтобы не указывать её в каждом SQL-запросе.

    Returns:
        psycopg2.connection: активное соединение с БД

    Raises:
        RuntimeError: если не удаётся подключиться к базе данных
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # Безопасная установка search_path через параметризированный запрос
            # SCHEMA_NAME - константа, определённая в этом же файле
            cur.execute('SET search_path TO %s' % psycopg2.extensions.quoted_identifier(SCHEMA_NAME))
        return conn
    except Exception as e:
        raise RuntimeError(f"Не удалось подключиться к базе данных: {e}") from e