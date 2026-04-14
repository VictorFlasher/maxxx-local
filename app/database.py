"""
Модуль подключения к базе данных PostgreSQL.
Автоматически устанавливает search_path на схему "maxxx-local".
"""

import os
import psycopg2
from psycopg2 import pool
from typing import Optional

# === Конфигурация подключения ===
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

    Returns:
        psycopg2.connection: активное соединение с БД

    Raises:
        psycopg2.OperationalError: если не удаётся подключиться
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{SCHEMA_NAME}"')
        return conn
    except Exception as e:
        raise RuntimeError(f"Не удалось подключиться к базе данных: {e}") from e