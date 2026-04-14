"""
Маршруты чата: WebSocket в реальном времени, создание чатов, история, загрузка файлов.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    File,
    BackgroundTasks
)
from pydantic import BaseModel

from ..database import get_db_connection
from .auth import get_current_user, get_current_user_from_header
from ..models.chat import create_private_chat, create_group_chat, is_user_in_chat, get_chat_history, \
    add_user_to_group_chat, remove_user_from_group_chat, get_user_chats, delete_private_chat, get_chat_type
from ..models.user import get_username
from fastapi import BackgroundTasks

# === Конфигурация ===
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_FILE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".txt", ".pdf"}
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 МБ

# === Глобальное хранилище WebSocket-соединений ===
# Структура: {chat_id: {user_id: websocket}}
active_connections: Dict[int, Dict[int, WebSocket]] = {}

router = APIRouter()

# === Модели запросов ===
class CreatePrivateChatRequest(BaseModel):
    user1_id: int
    user2_id: int

class CreateGroupChatRequest(BaseModel):
    name: str

# === Вспомогательные функции ===
def _get_chat_members(chat_id: int) -> List[int]:
    """
    Возвращает список ID всех участников чата (личного или группового).
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Определяем тип чата и получаем участников
        cur.execute("SELECT type, user1_id, user2_id FROM chats WHERE id = %s", (chat_id,))
        row = cur.fetchone()
        if not row:
            return []

        chat_type, user1, user2 = row

        if chat_type == 'private':
            return [user1, user2]
        elif chat_type == 'group':
            cur.execute("SELECT user_id FROM chat_members WHERE chat_id = %s", (chat_id,))
            return [r[0] for r in cur.fetchall()]
        else:
            return []
    finally:
        cur.close()
        conn.close()

async def _notify_users(chat_id: int, message: dict) -> None:
    """Рассылает сообщение всем активным участникам чата."""
    members = _get_chat_members(chat_id)
    for user_id in members:
        ws = active_connections.get(chat_id, {}).get(user_id)
        if ws:
            await ws.send_json(message)

# === WebSocket-маршрут ===
@router.websocket("/ws/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: int):
    """Обрабатывает WebSocket-соединение. Токен передаётся как ?token=..."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Токен не указан")
        return

    try:
        user_id = get_current_user(token)
    except ValueError:
        await websocket.close(code=4002, reason="Неверный токен")
        return

    if not is_user_in_chat(chat_id, user_id):
        await websocket.close(code=4003, reason="Нет доступа к чату")
        return

    await websocket.accept()

    if chat_id not in active_connections:
        active_connections[chat_id] = {}
    active_connections[chat_id][user_id] = websocket

    # Уведомление о входе
    await _notify_users(
        chat_id,
        {
            "type": "status",
            "user_id": user_id,
            "status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                text = payload.get("text", "").strip()
                if not text:
                    continue

                # === 1. Сохраняем сообщение в БД ===
                conn = get_db_connection()
                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        INSERT INTO messages (chat_id, sender_id, text, created_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (chat_id, user_id, text, datetime.now(timezone.utc)),
                    )
                    conn.commit()
                finally:
                    cur.close()
                    conn.close()

                # === 2. Готовим данные для рассылки ===
                chat_type = get_chat_type(chat_id)
                sender_username = None
                if chat_type == "group":
                    sender_username = get_username(user_id)

                # === 3. Рассылаем сообщение ===
                await _notify_users(
                    chat_id,
                    {
                        "type": "message",
                        "chat_id": chat_id,
                        "sender_id": user_id,
                        "sender_username": sender_username,
                        "chat_type": chat_type,
                        "text": text,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

            except json.JSONDecodeError:
                await websocket.send_json({"error": "Неверный JSON"})

    except WebSocketDisconnect:
        pass
    finally:
        active_connections.get(chat_id, {}).pop(user_id, None)
        await _notify_users(
            chat_id,
            {
                "type": "status",
                "user_id": user_id,
                "status": "offline",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

# === HTTP-маршруты ===
@router.post("/chats/private", summary="Создать личный чат")
def create_private_chat_endpoint(
    request: CreatePrivateChatRequest,
    current_user_id: int = Depends(get_current_user_from_header),
):
    if current_user_id not in (request.user1_id, request.user2_id):
        raise HTTPException(status_code=403, detail="Вы не участник этого чата")
    chat_id = create_private_chat(request.user1_id, request.user2_id)
    return {"chat_id": chat_id}

@router.post("/chats/group", summary="Создать групповой чат")
def create_group_chat_endpoint(
    request: CreateGroupChatRequest,
    current_user_id: int = Depends(get_current_user_from_header),
):
    """
    Создаёт новый групповой чат. Инициатор автоматически становится владельцем и участником.
    """
    chat_id = create_group_chat(request.name, current_user_id)
    return {"chat_id": chat_id}

@router.get("/chats/{chat_id}/messages", summary="Получить историю сообщений")
def get_messages(
    chat_id: int,
    limit: int = Query(50, le=100, description="Максимум 100 сообщений"),
    current_user_id: int = Depends(get_current_user_from_header),
):
    """
    Возвращает последние N сообщений из чата.
    Доступно только участникам чата.
    """
    if not is_user_in_chat(chat_id, current_user_id):
        raise HTTPException(
            status_code=403,
            detail="У вас нет доступа к этому чату"
        )

    history = get_chat_history(chat_id, limit)
    return {"messages": history}

@router.post("/chats/{chat_id}/upload", summary="Загрузить файл в чат")
async def upload_file(  # ← ОБЯЗАТЕЛЬНО async
    chat_id: int,
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_from_header),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Загружает файл в указанный чат. Поддерживаются только безопасные форматы.
    Максимальный размер файла: 2 МБ.
    """
    # Проверка участия в чате
    if not is_user_in_chat(chat_id, current_user_id):
        raise HTTPException(status_code=403, detail="Нет доступа к чату")

    # Проверка размера (для UploadFile нужно читать содержимое)
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс. 2 МБ)")

    # Возвращаемся к началу файла
    await file.seek(0)

    # Проверка расширения
    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in ALLOWED_FILE_EXTENSIONS:
        allowed = ", ".join(ALLOWED_FILE_EXTENSIONS)
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тип файла. Разрешены: {allowed}"
        )

    # Сохранение
    safe_filename = f"{uuid.uuid4().hex}{ext.lower()}"
    filepath = os.path.join(UPLOAD_DIR, safe_filename)

    with open(filepath, "wb") as f:
        f.write(contents)  # ← используем уже прочитанные данные

    # Фоновая задача
    background_tasks.add_task(
        _notify_file_upload,
        chat_id=chat_id,
        user_id=current_user_id,
        file_url=f"/uploads/{safe_filename}",
        file_type=ext.lower()
    )

    return {"file_url": f"/uploads/{safe_filename}"}

class InviteUserRequest(BaseModel):
    user_id: int

@router.get("/chats/me", summary="Получить список моих чатов")
def get_my_chats(current_user_id: int = Depends(get_current_user_from_header)):
    """Возвращает все чаты текущего пользователя."""
    return {"chats": get_user_chats(current_user_id)}

@router.post("/chats/{chat_id}/invite", summary="Пригласить пользователя в групповой чат")
def invite_user_to_chat(
    chat_id: int,
    request: InviteUserRequest,
    current_user_id: int = Depends(get_current_user_from_header)
):
    """
    Приглашает пользователя в групповой чат.
    Доступно только владельцу чата.
    """
    if not add_user_to_group_chat(chat_id, request.user_id, current_user_id):
        raise HTTPException(status_code=403, detail="Недостаточно прав или чат не найден")
    return {"status": "success"}

@router.delete("/chats/{chat_id}/leave", summary="Покинуть групповой чат")
def leave_group_chat(
    chat_id: int,
    current_user_id: int = Depends(get_current_user_from_header)
):
    """Позволяет пользователю покинуть групповой чат."""
    if not remove_user_from_group_chat(chat_id, current_user_id, current_user_id):
        raise HTTPException(status_code=403, detail="Невозможно покинуть чат")
    return {"status": "success"}

@router.delete("/chats/{chat_id}", summary="Удалить личный чат")
def delete_private_chat_endpoint(
    chat_id: int,
    current_user_id: int = Depends(get_current_user_from_header)
):
    """
    Удаляет личный чат. Доступно любому из участников.
    Групповые чаты нельзя удалять этим методом.
    """
    if not delete_private_chat(chat_id, current_user_id):
        raise HTTPException(status_code=403, detail="Нет доступа к чату или чат не найден")
    return {"status": "success", "message": "Чат удалён"}


async def _notify_file_upload(chat_id: int, user_id: int, file_url: str, file_type: str):
    """Фоновая задача: сохраняет файл в БД и уведомляет участников."""

    # 1. Сохраняем в БД
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO messages (chat_id, sender_id, file_path, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            (chat_id, user_id, file_url, datetime.now(timezone.utc)),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    # 2. Уведомляем через WebSocket
    chat_type = get_chat_type(chat_id)
    sender_username = None
    if chat_type == "group":
        sender_username = get_username(user_id)

    await _notify_users(
        chat_id,
        {
            "type": "message",
            "chat_id": chat_id,
            "sender_id": user_id,
            "sender_username": sender_username,
            "chat_type": chat_type,
            "text": None,
            "file_path": file_url,
            "file_type": file_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )