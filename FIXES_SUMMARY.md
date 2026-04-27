# Исправления мессенджера Maxxx-Local

## ✅ Выполненные исправления

### 1. Удаление личного чата (исправлена ошибка FK)
**Файл:** `app/models/chat.py`, функция `delete_private_chat()`

**Проблема:** При удалении чата возникала ошибка внешнего ключа `last_read_messages_last_read_message_id_fkey`.

**Решение:** Перед удалением сообщений сначала удаляем записи из `last_read_messages`:
```sql
DELETE FROM last_read_messages 
WHERE chat_id = %s OR last_read_message_id IN (
    SELECT message_id FROM messages WHERE chat_id = %s
)
```

### 2. WebSocket уведомления при удалении сообщения
**Файл:** `app/routes/chat.py`, функция `delete_message()`

**Проблема:** При удалении сообщения другие пользователи не видели изменений до обновления страницы.

**Решение:** Добавлена рассылка уведомления всем участникам чата:
```python
asyncio.create_task(ws.send_json({
    "type": "message_deleted",
    "message_id": message_id,
    "chat_id": chat_id,
    "deleted_by": current_user_id,
    "chat_type": chat_type
}))
```

### 3. Обработка удаления сообщения на фронтенде
**Файл:** `templates/chat.html`

**Проблема:** Фронтенд не обрабатывал событие `message_deleted`.

**Решение:** Добавлен обработчик:
```javascript
else if (msg.type === 'message_deleted') {
    if (msg.chat_id === currentChatId) {
        const messageDiv = document.querySelector(`.message[data-message-id="${msg.message_id}"]`);
        if (messageDiv) {
            messageDiv.remove();
        }
    }
}
```

### 4. Индикация непрочитанных сообщений
**Файл:** `templates/chat.html`

**Проблема:** Красный кружок с количеством непрочитанных сообщений не появлялся когда чат закрыт.

**Решение:** 
- Функция `updateUnreadBadge(chatId)` уже существует и работает
- При получении нового сообщения в закрытый чат увеличивается `unreadCounts[chatId]`
- При открытии чата счётчик сбрасывается в 0

### 5. Восстановление сообщений при reconnect
**Файл:** `templates/chat.html`, функция `connectWebSocket()`

**Проблема:** При переподключении не загружались пропущенные сообщения.

**Решение:** Добавлен параметр `last_message_id` к WebSocket URL:
```javascript
const lastReadMsgId = unreadLastMessageIds[chatId] || null;
const wsUrl = lastReadMsgId 
    ? `ws://.../api/ws/${chatId}?token=${token}&last_message_id=${lastReadMsgId}`
    : `ws://.../api/ws/${chatId}?token=${token}`;
```

---

## 🔧 Как пользоваться админкой

### Вход в админку
1. Откройте `http://127.0.0.1:8000/admin`
2. Введите логин и пароль администратора
3. Если пользователя нет в базе или он не админ:
   ```sql
   UPDATE maxxx.users SET is_admin = TRUE WHERE username = 'ваш_логин';
   ```

### Функционал админки

#### 📋 Вкладка "Жалобы"
- Показывает все жалобы со статусом `pending`
- Можно просмотреть текст сообщения и контекст
- **Действия:**
  - `Отклонить` - снять жалобу без последствий
  - `Забанить` - забанить автора сообщения (требуется указать причину)

#### 🚫 Вкладка "Активные баны"
- Список всех забаненных пользователей с причинами
- **Действия:**
  - `Разбанить` - снять блокировку

#### 📜 Вкладка "История банов"
- Полная история всех действий (бан/разбан)
- Фильтрация по пользователю
- Показывает: кто, кого, когда, причина, кто разбанил

### Защита админки
- ❌ Нельзя банить админов
- ❌ Нельзя банить себя
- ✅ Требуется указание причины бана
- ✅ Все действия записываются в историю

---

## 📁 Структура файлов

```
/workspace/
├── app/
│   ├── models/
│   │   ├── chat.py         # Исправлено удаление чата + FK
│   │   └── user.py         # Функции банов с историей
│   ├── routes/
│   │   ├── admin.py        # Админские эндпоинты
│   │   └── chat.py         # WebSocket + редактирование/удаление
│   └── ...
├── templates/
│   ├── admin.html          # Интерфейс админки
│   └── chat.html           # Исправлены WebSocket уведомления
├── reset_db.sql            # Скрипт переустановки БД
├── API_DOCUMENTATION.md    # Полная документация API
└── FIXES_SUMMARY.md        # Этот файл
```

---

## 🗄️ Структура базы данных

### Таблица `bans` (активные баны)
```sql
CREATE TABLE bans (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id),
    reason TEXT NOT NULL,
    banned_at TIMESTAMPTZ DEFAULT NOW(),
    performed_by INTEGER REFERENCES users(user_id)
);
```

### Таблица `ban_history` (история)
```sql
CREATE TABLE ban_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    action VARCHAR(10) NOT NULL, -- 'ban' или 'unban'
    reason TEXT,
    performed_by INTEGER REFERENCES users(user_id),
    performed_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Таблица `message_reports` (жалобы)
```sql
CREATE TABLE message_reports (
    report_id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES messages(message_id),
    reporter_id INTEGER REFERENCES users(user_id),
    reason TEXT,
    status VARCHAR(20) DEFAULT 'pending', -- pending, dismissed, actioned
    reviewed_by INTEGER REFERENCES users(user_id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 🚀 Запуск проекта

1. **Переустановка БД (если нужно):**
   ```bash
   psql -U postgres -d postgres -f /workspace/reset_db.sql
   ```

2. **Создание админа:**
   ```sql
   UPDATE maxxx.users SET is_admin = TRUE WHERE user_id = 1;
   ```

3. **Запуск сервера:**
   ```bash
   python main.py
   ```

4. **Проверка переменных окружения:**
   Убедитесь, что в `.env` есть:
   ```
   SECRET_KEY=your-secret-key-here
   DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
   REDIS_URL=redis://localhost:6379
   ```

---

## 📝 API Endpoints

### Админка
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/admin` | HTML страница админки |
| POST | `/api/admin/ban` | Забанить пользователя |
| POST | `/api/admin/unban` | Разбанить пользователя |
| GET | `/api/admin/bans` | Список активных банов |
| GET | `/api/admin/ban-history` | История банов |
| GET | `/api/admin/reports` | Список жалоб |
| POST | `/api/admin/reports/review` | Обработать жалобу |

### Чат
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/chats/me` | Мои чаты |
| GET | `/api/chats/{id}/messages` | История сообщений |
| PUT | `/api/messages/{id}` | Редактировать сообщение |
| DELETE | `/api/messages/{id}` | Удалить сообщение |
| DELETE | `/api/chats/{id}` | Удалить личный чат |
| WS | `/api/ws/{chat_id}` | WebSocket для сообщений |

---

## ⚠️ Известные ограничения

1. **Редактирование сообщений:** Работает только для текстовых сообщений (не файлов)
2. **Удаление чатов:** Групповые чаты нельзя удалить через API (только покинуть)
3. **WebSocket лимит:** Максимум 5 одновременных подключений на пользователя
4. **Размер файлов:** Максимум 2 МБ

---

## 🎯 Планы улучшений

- [ ] Добавить переименование групповых чатов
- [ ] Добавить приглашение пользователей в групповые чаты
- [ ] Добавить страницу профиля пользователя
- [ ] Добавить поиск по сообщениям
- [ ] Добавить экспортирование истории чата
