# Руководство по развёртыванию Maxxx-Local Chat

## 🔒 Безопасность и настройка

### 1. Переменные окружения

Скопируйте `.env.example` в `.env` и настройте параметры:

```bash
cp .env.example .env
```

**Обязательные параметры:**
- `SECRET_KEY` - минимум 32 случайных символа (сгенерируйте через `openssl rand -hex 32`)
- `DB_PASS` - надёжный пароль для PostgreSQL
- `ENVIRONMENT=production` - для production режима

### 2. База данных PostgreSQL

Скрипт инициализации БД находится в `app/init_db.sql`. Выполните его после создания БД:

```bash
psql -U postgres -d postgres -f app/init_db.sql
```

### 3. Redis (опционально, для масштабирования)

Для горизонтального масштабирования включите Redis:

```bash
REDIS_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
```

Установите Redis:
```bash
# Ubuntu/Debian
sudo apt install redis-server

# macOS
brew install redis
```

### 4. HTTPS/TLS

**В production обязательно используйте HTTPS!**

#### Вариант A: Nginx + Let's Encrypt (рекомендуется)

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Получите сертификат:
```bash
sudo certbot --nginx -d your-domain.com
```

#### Вариант B: Uvicorn с SSL

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 \
    --ssl-keyfile=./key.pem \
    --ssl-certfile=./cert.pem
```

### 5. Запуск приложения

#### Development режим:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Production режим:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

Или через Gunicorn:
```bash
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 6. Логирование

Логи сохраняются в директорию `logs/`:
- `logs/app.log` - основной лог файл
- Ротация логов: 10 MB, хранится 5 последних файлов

Для просмотра в реальном времени:
```bash
tail -f logs/app.log
```

### 7. Health Check

Эндпоинт для мониторинга:
```
GET /health
```

Ответ:
```json
{
    "status": "healthy",
    "timestamp": "2024-01-01T12:00:00Z"
}
```

### 8. Docker (опционально)

Пример `docker-compose.yml`:

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DB_HOST=db
      - DB_USER=postgres
      - DB_PASS=${DB_PASS}
      - SECRET_KEY=${SECRET_KEY}
      - REDIS_HOST=redis
      - REDIS_ENABLED=true
    depends_on:
      - db
      - redis
    
  db:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=${DB_PASS}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./app/init_db.sql:/docker-entrypoint-initdb.d/init.sql
    
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

## 📋 Чеклист перед запуском в production

- [ ] Сгенерирован уникальный `SECRET_KEY`
- [ ] Установлен надёжный пароль БД
- [ ] Настроен HTTPS
- [ ] `.env` добавлен в `.gitignore`
- [ ] Включено логирование в файл
- [ ] Настроен бэкап БД
- [ ] Настроен мониторинг health check
- [ ] Ограничен доступ к админским эндпоинтам
- [ ] Проведён security audit

## 🔧 Масштабирование

### Горизонтальное масштабирование

Для работы нескольких экземпляров приложения:

1. Включите Redis (`REDIS_ENABLED=true`)
2. Установите уникальный `INSTANCE_ID` для каждого экземпляра
3. Используйте балансировщик нагрузки (Nginx, HAProxy)

### Пул соединений БД

Пул настроен по умолчанию: min=2, max=10 соединений.
Настройте под вашу нагрузку в `main.py`:
```python
init_db_pool(minconn=5, maxconn=20)
```

### Rate Limiting

- HTTP запросы: 5-10 запросов в минуту (настроено в `app/routes/auth.py`)
- WebSocket: максимум 5 подключений на пользователя (настроено в Redis)

## 🐛 Отладка

### Просмотр логов
```bash
tail -f logs/app.log | grep ERROR
```

### Проверка подключения к БД
```bash
psql -h localhost -U postgres -d postgres -c "SELECT 1"
```

### Проверка Redis
```bash
redis-cli ping
```

### Тестирование API
```bash
curl http://localhost:8000/health
```
