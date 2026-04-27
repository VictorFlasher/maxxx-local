-- Исправление внешнего ключа для last_read_messages
-- Добавляем ON DELETE CASCADE чтобы сообщения удалялись корректно

-- Сначала удаляем старый constraint если он существует
ALTER TABLE last_read_messages 
DROP CONSTRAINT IF EXISTS last_read_messages_last_read_message_id_fkey;

-- Добавляем новый constraint с CASCADE
ALTER TABLE last_read_messages 
ADD CONSTRAINT last_read_messages_last_read_message_id_fkey 
FOREIGN KEY (last_read_message_id) 
REFERENCES messages(message_id) 
ON DELETE CASCADE;
