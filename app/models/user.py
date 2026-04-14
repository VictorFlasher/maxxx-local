"""
Модуль для работы с пользователями: регистрация, аутентификация, проверка прав.
Работает с таблицей users в схеме "maxxx-local".
"""

import bcrypt
import psycopg2
from typing import Optional, Tuple
from ..database import get_db_connection


def create_user(username: str, email: str, password: str) -> None:
    """
    Регистрирует нового пользователя с хешированным паролем.

    Args:
        username: уникальное имя пользователя
        email: уникальный email
        password: пароль в открытом виде (будет захеширован)

    Raises:
        ValueError: если пользователь с таким email или username уже существует
    """
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (username, email, password_hash)
            VALUES (%s, %s, %s)
            """,
            (username, email, hashed),
        )
        conn.commit()
    except psycopg2.IntegrityError as e:
        conn.rollback()
        raise ValueError("Пользователь с таким email или username уже существует") from e
    finally:
        cur.close()
        conn.close()


def get_user_by_email(email: str) -> Optional[Tuple[int, str, str]]:
    """
    Возвращает данные пользователя по email.

    Args:
        email: email пользователя

    Returns:
        Кортеж (id, email, password_hash) или None, если не найден
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, email, password_hash FROM users WHERE email = %s",
            (email,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def is_user_admin(user_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором.

    Args:
        user_id: ID пользователя

    Returns:
        True, если is_admin = true, иначе False
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()[0] == 'admin'
    finally:
        cur.close()
        conn.close()


def ban_user(target_user_id: int) -> bool:
    """
    Блокирует пользователя по ID.

    Args:
        target_user_id: ID пользователя для бана

    Returns:
        True, если пользователь был забанен, False — если не найден
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET is_banned = true WHERE id = %s",
            (target_user_id,),
        )
        updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        cur.close()
        conn.close()


def get_user_by_id(user_id: int) -> dict:
    """
    Возвращает данные пользователя по ID.

    Raises:
        ValueError: если пользователь не найден
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, username, email, role, is_banned
            FROM users
            WHERE id = %s
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Пользователь не найден")
        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "role": row[3],
            "is_banned": row[4]
        }
    finally:
        cur.close()
        conn.close()

def get_username(user_id: int) -> str:
    """Возвращает username по ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else f"Пользователь {user_id}"
    finally:
        cur.close()
        conn.close()