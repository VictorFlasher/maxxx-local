-- Таблица для жалоб на сообщения (используется в коде как message_reports)
CREATE TABLE IF NOT EXISTS message_reports (
    report_id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    reporter_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    reason TEXT,
    status VARCHAR(20) DEFAULT 'pending', -- pending, reviewed, dismissed, actioned
    reviewed_by INTEGER REFERENCES users(user_id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_reports_status ON message_reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_message ON message_reports(message_id);

-- Таблица для отслеживания прочитанных сообщений
CREATE TABLE IF NOT EXISTS last_read_messages (
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE,
    last_read_message_id INTEGER REFERENCES messages(message_id),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, chat_id)
);

CREATE INDEX IF NOT EXISTS idx_last_read_user_chat ON last_read_messages(user_id, chat_id);

-- Добавляем флаги для мягкого удаления чатов (если их еще нет)
-- Для личных чатов: удаляем у конкретного пользователя
-- Для групповых: автоматическое удаление при 0 участников обрабатывается в коде
ALTER TABLE chat_members ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;

-- Исправление ограничения check для connection_logs, если оно слишком строгое
-- Убедимся, что типы событий соответствуют тем, что мы шлем в коде
-- (обычно 'connect', 'disconnect', 'login' - проверьте ваше ограничение)
-- Если ошибка сохраняется, возможно нужно расширить ограничение в БД:
-- ALTER TABLE connection_logs DROP CONSTRAINT connection_logs_event_type_check;
-- ALTER TABLE connection_logs ADD CONSTRAINT connection_logs_event_type_check CHECK (event_type IN ('connect', 'disconnect', 'login', 'websocket_connect', 'websocket_disconnect'));
-- Но лучше использовать нормализованные значения в коде (что мы и сделали ранее).
