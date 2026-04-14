"""
Маршруты аутентификации: регистрация, вход, извлечение пользователя из токена.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from pydantic import BaseModel

from ..models.user import create_user, get_user_by_email
from ..models.user import get_user_by_id
import bcrypt
import os

# === Конфигурация JWT ===
SECRET_KEY = os.getenv("SECRET_KEY", "mysecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# === FastAPI компоненты ===
router = APIRouter()
oauth2_scheme = HTTPBearer()


# === Модели запросов ===
class UserRegister(BaseModel):
    """Данные для регистрации нового пользователя."""
    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    """Данные для входа в систему."""
    email: str
    password: str


# === Вспомогательные функции ===
def create_access_token(data: Dict[str, Any]) -> str:
    """
    Создаёт JWT-токен с заданными данными и временем жизни.

    Args:
        data: полезная нагрузка (например, {"user_id": 123})

    Returns:
        Подписанный JWT-токен
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


# === Роутеры ===
@router.post("/register", summary="Регистрация нового пользователя")
def register(user: UserRegister):
    """Создаёт нового пользователя. Пароль хешируется автоматически."""
    try:
        create_user(user.username, user.email, user.password)
        return {"message": "Пользователь создан"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", summary="Вход в систему")
def login(user: UserLogin):
    """Аутентифицирует пользователя и возвращает JWT-токен."""
    db_user = get_user_by_email(user.email)
    if not db_user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    stored_hash = db_user[2]
    if not bcrypt.checkpw(user.password.encode("utf-8"), stored_hash.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    token = create_access_token({"sub": db_user[1], "user_id": db_user[0]})
    return {"access_token": token, "token_type": "bearer"}


def get_current_user_from_header(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)
) -> int:
    """
    Извлекает user_id из токена и проверяет:
    - валидность токена
    - существование пользователя
    - статус бана
    """
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Неверный токен")
        user_id = int(user_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Неверный токен")

    # Проверяем, существует ли пользователь и не забанен ли
    try:
        user = get_user_by_id(user_id)
        if user["is_banned"]:
            raise HTTPException(status_code=403, detail="Вы забанены")
    except ValueError:
        raise HTTPException(status_code=401, detail="Пользователь не найден")

    return user_id


# === Утилита для WebSocket (не использует заголовки) ===
def get_current_user(token: str) -> int:
    """
    Извлекает user_id из строки токена (для WebSocket).
    Выбрасывает ValueError при ошибке — обрабатывается вручную.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise ValueError("Нет user_id в токене")
        return int(user_id)
    except Exception as e:
        raise ValueError("Неверный токен") from e