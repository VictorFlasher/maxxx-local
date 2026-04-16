"""
Модуль для работы с пользователями: регистрация, аутентификация, проверка прав.
Работает с таблицей users в схеме "maxxx-local".

Функции модуля:
- Регистрация новых пользователей с хешированием паролей
- Аутентификация по email
- Поиск пользователей по username/email
- Проверка административных прав и банов
- Управление статусом пользователей
"""

import re
import bcrypt
import psycopg2
from typing import Optional, Tuple, List
from ..database import get_db_connection, release_db_connection


def create_user(username: str, email: str, password: str, secure_hash: bool = True) -> None:
    """
    Регистрирует нового пользователя с хешированным паролем.

    Args:
        username: уникальное имя пользователя
        email: уникальный email (должен содержать @ и домен)
        password: пароль в открытом виде (будет захеширован)
        secure_hash: если True, использует безопасное хеширование с очисткой памяти

    Raises:
        ValueError: если пользователь с таким email или username уже существует, 
                    или email некорректен
    """
    # Проверка формата email
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise ValueError("Некорректный формат email")
    
    email = email.lower()  # Приводим к нижнему регистру
    
    # Безопасное хеширование пароля с очисткой памяти
    password_bytes = None
    hashed = None
    try:
        # Преобразуем строку пароля в bytes для bcrypt
        password_bytes = bytearray(password.encode('utf-8'))
        # bcrypt.hashpw принимает bytes или bytearray, но для надёжности явно конвертируем
        hashed = bcrypt.hashpw(bytes(password_bytes), bcrypt.gensalt()).decode("utf-8")
    finally:
        # Очищаем память от пароля
        if password_bytes is not None:
            for i in range(len(password_bytes)):
                password_bytes[i] = 0
            del password_bytes
    
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
        release_db_connection(conn)


def get_user_by_email(email: str) -> Optional[Tuple[int, str, str]]:
    """
    Возвращает данные пользователя по email.

    Args:
        email: email пользователя

    Returns:
        Кортеж (user_id, email, password_hash) или None, если не найден
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT user_id, email, password_hash FROM users WHERE email = %s",
            (email,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        release_db_connection(conn)


def get_user_by_email_or_username(email_or_username: str) -> Optional[Tuple[int, str, str]]:
    """
    Возвращает данные пользователя по email или username.

    Args:
        email_or_username: email или username пользователя

    Returns:
        Кортеж (user_id, email, username) или None, если не найден
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT user_id, email, username FROM users 
               WHERE email = %s OR username = %s""",
            (email_or_username, email_or_username),
        )
        return cur.fetchone()
    finally:
        cur.close()
        release_db_connection(conn)


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
        cur.execute("SELECT is_admin FROM users WHERE user_id = %s", (user_id,))
        return cur.fetchone()[0] == True
    finally:
        cur.close()
        release_db_connection(conn)


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
            "UPDATE users SET is_banned = true WHERE user_id = %s",
            (target_user_id,),
        )
        updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        cur.close()
        release_db_connection(conn)


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
            SELECT user_id, username, email, is_admin, is_banned
            FROM users
            WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Пользователь не найден")
        return {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "is_admin": row[3],
            "is_banned": row[4]
        }
    finally:
        cur.close()
        release_db_connection(conn)

def get_username(user_id: int) -> str:
    """Возвращает username по ID."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT username FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else f"Пользователь {user_id}"
    finally:
        cur.close()
        release_db_connection(conn)


def get_username_cached(user_id: int) -> str:
    """
    Возвращает username по ID с кэшированием в Redis.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Username или 'Пользователь {user_id}' если не найден
    """
    from ..utils.redis_manager import redis_cache_get, redis_cache_set
    
    cache_key = f"username:{user_id}"
    
    # Проверяем кэш
    cached = redis_cache_get(cache_key)
    if cached is not None:
        return cached
    
    # Получаем из БД
    username = get_username(user_id)
    
    # Сохраняем в кэш
    redis_cache_set(cache_key, username, ttl=600)
    
    return username


def get_all_users(exclude_user_id: Optional[int] = None) -> List[dict]:
    """
    Возвращает список всех пользователей (кроме текущего).
    
    Args:
        exclude_user_id: ID пользователя, которого нужно исключить из списка
        
    Returns:
        Список словарей с информацией о пользователях
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if exclude_user_id:
            cur.execute("""
                SELECT user_id, username, email
                FROM users
                WHERE user_id != %s
                ORDER BY username
            """, (exclude_user_id,))
        else:
            cur.execute("""
                SELECT user_id, username, email
                FROM users
                ORDER BY username
            """)
        
        rows = cur.fetchall()
        return [
            {"id": row[0], "username": row[1], "email": row[2]}
            for row in rows
        ]
    finally:
        cur.close()
        release_db_connection(conn)


def search_users(query: str, exclude_user_id: Optional[int] = None) -> List[dict]:
    """
    Ищет пользователей по имени или email.
    
    Args:
        query: Строка поиска
        exclude_user_id: ID пользователя, которого нужно исключить из результатов
        
    Returns:
        Список словарей с информацией о найденных пользователях
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        search_pattern = f"%{query}%"
        
        if exclude_user_id:
            cur.execute("""
                SELECT user_id, username, email
                FROM users
                WHERE (username ILIKE %s OR email ILIKE %s)
                  AND user_id != %s
                ORDER BY username
            """, (search_pattern, search_pattern, exclude_user_id))
        else:
            cur.execute("""
                SELECT user_id, username, email
                FROM users
                WHERE username ILIKE %s OR email ILIKE %s
                ORDER BY username
            """, (search_pattern, search_pattern))
        
        rows = cur.fetchall()
        return [
            {"id": row[0], "username": row[1], "email": row[2]}
            for row in rows
        ]
    finally:
        cur.close()
        release_db_connection(conn)