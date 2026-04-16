"""
Административные маршруты: бан пользователей, просмотр и обработка жалоб.
Требуется авторизация и права администратора.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from ..models.user import is_user_admin, ban_user, get_db_connection, release_db_connection
from .auth import get_current_user_from_header


router = APIRouter()


class BanUserRequest(BaseModel):
    """Запрос на блокировку пользователя."""
    user_id: int


class ReportResponse(BaseModel):
    """Ответ с информацией о жалобе."""
    report_id: int
    message_id: int
    reporter_id: int
    reason: str
    status: str
    created_at: datetime
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    message_text: str
    sender_id: int
    chat_id: int


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


@router.get("/admin/reports", summary="Получить список жалоб", response_model=List[ReportResponse])
def get_reports(
    status: Optional[str] = "pending",
    limit: int = 50,
    current_user_id: int = Depends(get_current_user_from_header),
):
    """
    Получает список жалоб для модерации.
    
    - status: фильтр по статусу ('pending', 'reviewed', 'resolved')
    - limit: максимальное количество записей
    """
    if not is_user_admin(current_user_id):
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT 
                r.report_id, r.message_id, r.reporter_id, r.reason, 
                r.status, r.created_at, r.reviewed_by, r.reviewed_at,
                m.text as message_text, m.sender_id, m.chat_id
            FROM message_reports r
            JOIN messages m ON r.message_id = m.message_id
        """
        params = []
        
        if status:
            query += " WHERE r.status = %s"
            params.append(status)
        
        query += " ORDER BY r.created_at DESC LIMIT %s"
        params.append(limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        reports = []
        for row in rows:
            reports.append(ReportResponse(
                report_id=row[0],
                message_id=row[1],
                reporter_id=row[2],
                reason=row[3],
                status=row[4],
                created_at=row[5],
                reviewed_by=row[6],
                reviewed_at=row[7],
                message_text=row[8],
                sender_id=row[9],
                chat_id=row[10]
            ))
        
        return reports
    finally:
        cur.close()
        release_db_connection(conn)


class ReviewReportRequest(BaseModel):
    """Запрос на обработку жалобы."""
    report_id: int
    status: str  # 'reviewed' или 'resolved'
    action: Optional[str] = None  # 'ban_sender', 'delete_message', None


@router.post("/admin/reports/review", summary="Обработать жалобу")
def review_report(
    request: ReviewReportRequest,
    current_user_id: int = Depends(get_current_user_from_header),
):
    """
    Обрабатывает жалобу: меняет статус и optionally выполняет действие.
    
    Действия:
    - ban_sender: забанить автора сообщения
    - delete_message: удалить сообщение
    - None: просто отметить как обработанную
    """
    if not is_user_admin(current_user_id):
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Проверяем существование жалобы и получаем данные
        cur.execute("""
            SELECT r.message_id, m.sender_id 
            FROM message_reports r
            JOIN messages m ON r.message_id = m.message_id
            WHERE r.report_id = %s
        """, (request.report_id,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Жалоба не найдена")
        
        message_id, sender_id = row
        
        # Обновляем статус жалобы
        cur.execute("""
            UPDATE message_reports 
            SET status = %s, reviewed_by = %s, reviewed_at = NOW()
            WHERE report_id = %s
        """, (request.status, current_user_id, request.report_id))
        
        # Выполняем действие если указано
        if request.action == 'ban_sender':
            cur.execute("UPDATE users SET is_banned = TRUE WHERE user_id = %s", (sender_id,))
        elif request.action == 'delete_message':
            cur.execute("DELETE FROM messages WHERE message_id = %s", (message_id,))
        
        conn.commit()
        return {"status": "success", "action": request.action}
    except HTTPException:
        raise
    finally:
        cur.close()
        release_db_connection(conn)