-- =============================================================================
-- Скрипт полной переустановки базы данных Maxxx-Local Chat
-- ВНИМАНИЕ: Этот скрипт УДАЛЯЕТ все существующие данные в схеме maxxx!
-- =============================================================================

-- 1. Очистка старой схемы
DROP SCHEMA IF EXISTS maxxx CASCADE;
CREATE SCHEMA maxxx;
SET search_path TO "maxxx";

-- =============================================================================
-- 2. Таблицы пользователей и прав доступа
-- =============================================================================

-- Таблица пользователей
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,          -- Флаг администратора
    is_banned BOOLEAN DEFAULT FALSE,         -- Текущий статус бана
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 3. Таблицы банов и истории модерации
-- =============================================================================

-- Активные баны (для быстрого доступа и причин)
CREATE TABLE bans (
    ban_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    banned_by INTEGER REFERENCES users(user_id), -- Кто забанил (может быть NULL если системный)
    reason TEXT NOT NULL,                        -- Причина бана
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id) -- У пользователя может быть только один активный бан в этой таблице
);

-- Полная история банов (аудит)
CREATE TABLE ban_history (
    history_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    action VARCHAR(20) NOT NULL CHECK (action IN ('ban', 'unban')), -- Действие
    performed_by INTEGER REFERENCES users(user_id), -- Кто выполнил действие
    reason TEXT,                                    -- Причина (для бана) или комментарий (для разбана)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрой выборки истории
CREATE INDEX idx_ban_history_user ON ban_history(user_id);
CREATE INDEX idx_ban_history_action ON ban_history(action);

-- =============================================================================
-- 4. Чаты и сообщения
-- =============================================================================

-- Таблица чатов
CREATE TABLE chats (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) NOT NULL CHECK (type IN ('private', 'group')),
    name VARCHAR(255),                -- Название для групп, NULL для личных
    user1_id INTEGER REFERENCES users(user_id), -- Для private: участник 1
    user2_id INTEGER REFERENCES users(user_id), -- Для private: участник 2
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(user_id), -- Создатель (для групп)
    owner_id INTEGER REFERENCES users(user_id)    -- Владелец (может передаваться)
);

-- Участники групповых чатов
CREATE TABLE chat_members (
    chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE, -- Мягкое удаление (пользователь скрыл чат)
    PRIMARY KEY (chat_id, user_id)
);

-- Сообщения
CREATE TABLE messages (
    message_id SERIAL PRIMARY KEY,
    chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE,
    sender_id INTEGER REFERENCES users(user_id),
    text TEXT,
    file_path VARCHAR(500),
    file_type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    edited_at TIMESTAMP WITH TIME ZONE, -- Время последнего редактирования
    is_deleted BOOLEAN DEFAULT FALSE    -- Мягкое удаление сообщения
);

-- Индексы для сообщений
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);

-- =============================================================================
-- 5. Жалобы (Reports)
-- =============================================================================

CREATE TABLE message_reports (
    report_id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    reporter_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    reason TEXT,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'reviewed', 'dismissed', 'actioned')),
    reviewed_by INTEGER REFERENCES users(user_id), -- Админ, рассмотревший жалобу
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для жалоб
CREATE INDEX idx_reports_status ON message_reports(status);
CREATE INDEX idx_reports_message ON message_reports(message_id);

-- =============================================================================
-- 6. Прочее (Логи, прочитанные сообщения)
-- =============================================================================

-- История подключений
CREATE TABLE connection_logs (
    log_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id),
    event_type VARCHAR(30) NOT NULL, -- connect, disconnect, login, ws_connect и т.д.
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Статус прочтения сообщений
CREATE TABLE last_read_messages (
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE,
    last_read_message_id INTEGER REFERENCES messages(message_id),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, chat_id)
);

CREATE INDEX idx_last_read_user_chat ON last_read_messages(user_id, chat_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_chat_members_user_id ON chat_members(user_id);

-- =============================================================================
-- 7. Начальные данные (Тестовый админ)
-- =============================================================================
-- Пароль: admin123 (хэш должен быть сгенерирован приложением, здесь заглушка для примера структуры)
-- В реальном приложении создайте админа через регистрацию с повышенными правами или скрипт
-- INSERT INTO users (username, email, password_hash, is_admin) VALUES ...
