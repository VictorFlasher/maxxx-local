# main.py
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates  # ← добавили

from app.routes import auth, config, chat, admin

app = FastAPI(
    title="Maxxx-Local Chat API",
    description="Безопасный многопользовательский чат",
    version="1.0.0",
)

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