"""
Административные маршруты: бан пользователей.
Требуется авторизация и права администратора.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..models.user import is_user_admin, ban_user
from .auth import get_current_user_from_header


router = APIRouter()


class BanUserRequest(BaseModel):
    """Запрос на блокировку пользователя."""
    user_id: int


@router.post("/admin/ban", summary="Забанить пользователя")
def ban_user_endpoint(
    request: BanUserRequest,
    current_user_id: int = Depends(get_current_user_from_header),
):
    """
    Блокирует указанного пользователя. Доступно только администраторам.

    - Нельзя забанить самого себя
    - Нельзя забанить несуществующего пользователя
    """
    # Проверка прав администратора
    if not is_user_admin(current_user_id):
        raise HTTPException(status_code=403, detail="Требуются права администратора")

    target_id = request.user_id

    # Защита от самобана
    if target_id == current_user_id:
        raise HTTPException(status_code=400, detail="Нельзя забанить себя")

    # Выполнение бана
    if not ban_user(target_id):
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return {"status": "success", "banned_user_id": target_id}