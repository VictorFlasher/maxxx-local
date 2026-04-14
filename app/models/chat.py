"""
Модуль для работы с чатами: создание, проверка участия, получение истории.
Использует единую таблицу 'chats' для всех типов чатов.
"""
import os
from typing import List, Dict, Any, Optional
import psycopg2
from ..database import get_db_connection

def create_private_chat(user1_id: int, user2_id: int) -> int:
    """
    Создаёт или возвращает существующий личный чат между двумя пользователями.

    Args:
        user1_id: ID первого пользователя
        user2_id: ID второго пользователя

    Returns:
        ID чата

    Raises:
        ValueError: если user1_id == user2_id или чат не удалось создать
    """
    if user1_id == user2_id:
        raise ValueError("Нельзя создать чат с самим собой")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Ищем существующий чат
        cur.execute("""
            SELECT id FROM chats
            WHERE type = 'private'
              AND (
                  (user1_id = %s AND user2_id = %s)
                  OR
                  (user1_id = %s AND user2_id = %s)
              )
        """, (user1_id, user2_id, user2_id, user1_id))

        row = cur.fetchone()
        if row:
            return row[0]

        # Создаём новый чат
        cur.execute("""
            INSERT INTO chats (type, user1_id, user2_id)
            VALUES ('private', %s, %s)
            RETURNING id
        """, (user1_id, user2_id))

        chat_id = cur.fetchone()[0]
        conn.commit()
        return chat_id

    except psycopg2.IntegrityError:
        conn.rollback()
        # Повторная попытка найти чат (гонка условий)
        cur.execute("""
            SELECT id FROM chats
            WHERE type = 'private'
              AND (
                  (user1_id = %s AND user2_id = %s)
                  OR
                  (user1_id = %s AND user2_id = %s)
              )
        """, (user1_id, user2_id, user2_id, user1_id))
        row = cur.fetchone()
        if row:
            return row[0]
        raise ValueError("Не удалось создать чат")
    finally:
        cur.close()
        conn.close()

def create_group_chat(name: str, owner_id: int) -> int:
    """
    Создаёт новый групповой чат.

    Args:
        name: название чата
        owner_id: ID создателя

    Returns:
        ID чата
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO chats (type, name, owner_id)
            VALUES ('group', %s, %s)
            RETURNING id
        """, (name, owner_id))
        chat_id = cur.fetchone()[0]
        conn.commit()
        return chat_id
    finally:
        cur.close()
        conn.close()

def is_user_in_chat(chat_id: int, user_id: int) -> bool:
    """
    Проверяет, состоит ли пользователь в указанном чате.

    Args:
        chat_id: ID чата
        user_id: ID пользователя

    Returns:
        True, если пользователь — участник чата
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Сначала определим тип чата
        cur.execute("SELECT type, user1_id, user2_id FROM chats WHERE id = %s", (chat_id,))
        row = cur.fetchone()
        if not row:
            return False

        chat_type, user1, user2 = row

        if chat_type == 'private':
            return user_id in (user1, user2)
        elif chat_type == 'group':
            cur.execute(
                "SELECT 1 FROM chat_members WHERE chat_id = %s AND user_id = %s",
                (chat_id, user_id)
            )
            return cur.fetchone() is not None
        else:
            return False
    finally:
        cur.close()
        conn.close()

def get_chat_history(chat_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT m.sender_id, u.username, m.text, m.file_path, m.created_at, c.type
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            JOIN chats c ON m.chat_id = c.id
            WHERE m.chat_id = %s
            ORDER BY m.created_at ASC
            LIMIT %s
        """, (chat_id, limit))

        rows = cur.fetchall()
        result = []
        for row in rows:
            chat_type = row[5]
            msg = {
                "sender_id": row[0],
                "text": row[2],
                "file_path": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
                "chat_type": chat_type
            }

            # Определяем тип файла
            if row[3]:  # есть file_path
                _, ext = os.path.splitext(row[3])
                msg["file_type"] = ext.lower()

            # Только для групповых чатов добавляем имя
            if chat_type == "group":
                msg["sender_username"] = row[1]
            result.append(msg)

        return result
    finally:
        cur.close()
        conn.close()

def get_user_chats(user_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает список чатов для конкретного пользователя.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        chats = []

        # Личные чаты
        cur.execute("""
            SELECT c.id, u1.username AS user1_name, u2.username AS user2_name,
                   c.user1_id, c.user2_id
            FROM chats c
            JOIN users u1 ON c.user1_id = u1.id
            JOIN users u2 ON c.user2_id = u2.id
            WHERE c.type = 'private' AND (c.user1_id = %s OR c.user2_id = %s)
        """, (user_id, user_id))

        for row in cur.fetchall():
            chat_id, user1_name, user2_name, user1_id, user2_id = row

            # Определяем, кто "другой" пользователь
            if user1_id == user_id:
                other_name = user2_name
            else:
                other_name = user1_name

            chats.append({
                "chat_id": chat_id,
                "type": "private",
                "name": f"Чат с {other_name}"
            })

        # Групповые чаты (без изменений)
        cur.execute("""
            SELECT c.id, c.name
            FROM chats c
            JOIN chat_members cm ON c.id = cm.chat_id
            WHERE c.type = 'group' AND cm.user_id = %s
        """, (user_id,))

        for row in cur.fetchall():
            chats.append({
                "chat_id": row[0],
                "type": "group",
                "name": row[1]
            })

        return chats
    finally:
        cur.close()
        conn.close()

def add_user_to_group_chat(chat_id: int, user_id: int, inviter_id: int) -> bool:
    """
    Добавляет пользователя в групповой чат.
    Только владелец чата может приглашать.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Проверяем, что чат групповой и inviter — владелец
        cur.execute("""
            SELECT owner_id FROM chats
            WHERE id = %s AND type = 'group'
        """, (chat_id,))
        row = cur.fetchone()
        if not row or row[0] != inviter_id:
            return False

        # Добавляем участника
        cur.execute("""
            INSERT INTO chat_members (chat_id, user_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (chat_id, user_id))
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()

def remove_user_from_group_chat(chat_id: int, user_id: int, remover_id: int) -> bool:
    """
    Удаляет пользователя из группового чата.
    Может сделать владелец или сам пользователь (покинуть чат).
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Проверяем, что чат групповой
        cur.execute("SELECT owner_id FROM chats WHERE id = %s AND type = 'group'", (chat_id,))
        row = cur.fetchone()
        if not row:
            return False

        owner_id = row[0]
        # Разрешено: владелец удаляет кого угодно, или пользователь удаляет себя
        if remover_id != owner_id and remover_id != user_id:
            return False

        cur.execute("DELETE FROM chat_members WHERE chat_id = %s AND user_id = %s", (chat_id, user_id))
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()

def delete_private_chat(chat_id: int, user_id: int) -> bool:
    """
    Удаляет личный чат. Любой из участников может удалить.
    Удаляются также все сообщения в этом чате.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Проверяем, что чат существует, личный и пользователь — участник
        cur.execute("""
            SELECT user1_id, user2_id FROM chats
            WHERE id = %s AND type = 'private'
        """, (chat_id,))
        row = cur.fetchone()
        if not row or user_id not in (row[0], row[1]):
            return False

        # Удаляем чат и все сообщения
        cur.execute("DELETE FROM messages WHERE chat_id = %s", (chat_id,))
        cur.execute("DELETE FROM chats WHERE id = %s", (chat_id,))
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()

def get_chat_type(chat_id: int) -> str:
    """Возвращает тип чата: 'private' или 'group'."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT type FROM chats WHERE id = %s", (chat_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()
        conn.close()