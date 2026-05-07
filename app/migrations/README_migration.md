# Инструкция по применению миграции

## Проблема
При загрузке файлов в чат возникает ошибка:
```
psycopg2.errors.UndefinedColumn: столбец "file_path" в таблице "messages" не существует
```

## Решение
Необходимо добавить новые колонки в таблицу `messages`:
- `file_path` — путь/URL к файлу
- `file_type` — тип файла (расширение)

## Как выполнить миграцию

### Вариант 1: Через SQL файл (рекомендуется)
```bash
psql -U postgres -d postgres -f app/migrations/add_file_support_to_messages.sql
```

Или подключитесь к БД вручную:
```bash
psql -U postgres -d postgres
```

Затем выполните:
```sql
\i app/migrations/add_file_support_to_messages.sql
```

### Вариант 2: Прямой SQL запрос
Если у вас схема `maxxx_local` (как в .env):
```sql
SET search_path TO maxxx_local;

ALTER TABLE messages 
ADD COLUMN IF NOT EXISTS file_path VARCHAR(500);

ALTER TABLE messages 
ADD COLUMN IF NOT EXISTS file_type VARCHAR(50);

CREATE INDEX IF NOT EXISTS idx_messages_file_path ON messages(file_path) WHERE file_path IS NOT NULL;
```

### Вариант 3: Автоматическое применение через Python
Код уже обновлён и будет **автоматически адаптироваться** под структуру вашей БД:
- Если колонок нет → сохранит файл как `[Файл]: URL` в поле `content`
- Если есть только `file_path` → использует его
- Если есть обе колонки → использует полную версию с `file_path` и `file_type`

**Но для полноценной работы рекомендуется выполнить миграцию БД!**

## Проверка
После применения миграции проверьте, что колонки добавлены:
```sql
\dt maxxx_local.messages
\d maxxx_local.messages
```

Вы должны увидеть:
- `file_path character varying(500)`
- `file_type character varying(50)`

## Примечание
Миграция безопасна — используется `IF NOT EXISTS`, поэтому повторное выполнение не вызовет ошибок.

## Что было изменено в коде
1. **app/routes/chat.py** — функция `_notify_file_upload()` теперь проверяет наличие колонок перед INSERT
2. **app/database.py** — добавлена функция `get_schema_name()` для динамического получения имени схемы
3. **app/migrations/add_file_support_to_messages.sql** — скрипт миграции БД
4. **app/migrations/README_migration.md** — эта инструкция
