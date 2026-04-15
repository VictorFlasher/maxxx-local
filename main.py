# main.py
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates  # ← добавили
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from app.routes import auth, config, chat, admin
from app.routes.auth import limiter  # Импортируем экземпляр лимитера

app = FastAPI(
    title="Maxxx-Local Chat API",
    description="Безопасный многопользовательский чат",
    version="1.0.0",
)

def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Обработчик превышения лимита запросов."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Слишком много запросов. Пожалуйста, попробуйте позже."},
    )

# Подключаем SlowAPI к приложению
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Шаблоны
templates = Jinja2Templates(directory="templates")

# Статика
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploaded_files")

# Роутеры
app.include_router(auth.router, prefix="/api", tags=["Аутентификация"])
app.include_router(config.router, prefix="/api", tags=["Конфигурация"])
app.include_router(chat.router, prefix="/api", tags=["Чат"])
app.include_router(admin.router, prefix="/api", tags=["Администрирование"])

# Фронтенд-маршрут
@app.get("/")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/chat")
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/search-users")
async def search_users_page(request: Request):
    """Страница поиска пользователей."""
    return templates.TemplateResponse("search_users.html", {"request": request})