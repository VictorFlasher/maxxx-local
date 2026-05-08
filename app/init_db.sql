-- ============================================================================
-- Инициализация базы данных Maxxx Local
-- Схема: maxxx_local
-- ============================================================================
-- Использование: psql -U postgres -d postgres -f app/init_db.sql

-- 1. Создаём схему (если не существует)
CREATE SCHEMA IF NOT EXISTS maxxx_local;

-- Переключаемся на схему maxxx_local для всех последующих операций
SET search_path TO maxxx_local;

-- ============================================================================
-- ОСНОВНЫЕ ТАБЛИЦЫ
-- ============================================================================

-- Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    is_banned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE
);

-- Таблица чатов
CREATE TABLE IF NOT EXISTS chats (
    chat_id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    is_group BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL
);

-- Таблица участников чата
CREATE TABLE IF NOT EXISTS chat_members (
    chat_id INTEGER REFERENCES chats(chat_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    role VARCHAR(50) DEFAULT 'member',
    PRIMARY KEY (chat_id, user_id)
);

-- Таблица сообщений с поддержкой файлов
CREATE TABLE IF NOT EXISTS messages (
    message_id SERIAL PRIMARY KEY,
    chat_id INTEGER REFERENCES chats(chat_id) ON DELETE CASCADE,
    sender_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    content TEXT,                      -- Текст сообщения или NULL для файлов
    file_path VARCHAR(500),            -- Путь к файлу
    file_type VARCHAR(50),             -- Тип файла (image/png, application/pdf)
    original_filename VARCHAR(255),    -- Оригинальное имя файла
    encrypted_key BYTEA,               -- Ключ шифрования (опционально)
    iv BYTEA,                          -- Вектор инициализации
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_edited BOOLEAN DEFAULT FALSE,
    edited_at TIMESTAMP WITH TIME ZONE
);

-- Таблица активных банов
CREATE TABLE IF NOT EXISTS bans (
    ban_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE UNIQUE,
    banned_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Таблица истории банов
CREATE TABLE IF NOT EXISTS ban_history (
    history_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL CHECK (action IN ('ban', 'unban')),
    performed_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Триггер для автоматического добавления записи в ban_history при бане
CREATE OR REPLACE FUNCTION add_ban_history_entry()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO ban_history (user_id, action, performed_by, reason)
    VALUES (NEW.user_id, 'ban', NEW.banned_by, NEW.reason);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ban_history_insert ON bans;
CREATE TRIGGER trg_ban_history_insert
    AFTER INSERT ON bans
    FOR EACH ROW
    EXECUTE FUNCTION add_ban_history_entry();

-- Триггер для автоматического добавления записи в ban_history при разбане
CREATE OR REPLACE FUNCTION add_unban_history_entry()
RETURNS TRIGGER AS $$
BEGIN
    -- При удалении из bans (разбан) НЕ добавляем запись, 
    -- так как она уже добавлена вручную с причиной разбана
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ban_history_delete ON bans;
CREATE TRIGGER trg_ban_history_delete
    AFTER DELETE ON bans
    FOR EACH ROW
    EXECUTE FUNCTION add_unban_history_entry();

-- Таблица жалоб на сообщения
CREATE TABLE IF NOT EXISTS message_reports (
    report_id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES messages(message_id) ON DELETE CASCADE,
    reporter_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'reviewed', 'resolved', 'actioned')),
    reviewed_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Триггер для автоматического скрытия жалоб при бане пользователя
CREATE OR REPLACE FUNCTION resolve_reports_on_user_ban()
RETURNS TRIGGER AS $$
BEGIN
    -- При бане пользователя помечаем все его pending жалобы как resolved
    UPDATE maxxx_local.message_reports
    SET status = 'resolved', reviewed_at = NOW()
    WHERE message_id IN (
        SELECT message_id FROM maxxx_local.messages WHERE sender_id = NEW.user_id
    )
    AND status = 'pending';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_resolve_reports_on_ban ON bans;
CREATE TRIGGER trg_resolve_reports_on_ban
    AFTER INSERT ON bans
    FOR EACH ROW
    EXECUTE FUNCTION resolve_reports_on_user_ban();

-- Таблица логов подключений
CREATE TABLE IF NOT EXISTS connection_logs (
    log_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- ИНДЕКСЫ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_file_path ON messages(file_path) WHERE file_path IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_members_user_id ON chat_members(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_members_chat_id ON chat_members(chat_id);
CREATE INDEX IF NOT EXISTS idx_bans_user_id ON bans(user_id);
CREATE INDEX IF NOT EXISTS idx_ban_history_user_id ON ban_history(user_id);
CREATE INDEX IF NOT EXISTS idx_message_reports_status ON message_reports(status);
CREATE INDEX IF NOT EXISTS idx_message_reports_message_id ON message_reports(message_id);
CREATE INDEX IF NOT EXISTS idx_connection_logs_user_id ON connection_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_connection_logs_created_at ON connection_logs(created_at);

-- ============================================================================
-- ЗАВЕРШЕНИЕ
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'База данных maxxx_local успешно инициализирована!';
    RAISE NOTICE 'Создано таблиц: 8 (users, chats, chat_members, messages, bans, ban_history, message_reports, connection_logs)';
    RAISE NOTICE 'Создано триггеров: 3 (ban_history_insert, resolve_reports_on_ban)';
END $$;
