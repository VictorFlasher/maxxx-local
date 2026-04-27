"""
Модуль для работы с Redis: распределённое хранилище состояний WebSocket и кэширование.

Этот модуль предоставляет:
- Подключение к Redis для распределённого хранения состояний
- Управление активными WebSocket-соединениями across multiple instances
- Кэширование часто запрашиваемых данных
- Механизм rate-limiting для WebSocket подключений
"""

import json
import logging
import os
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timezone
import redis.asyncio as aioredis
from redis import Redis

logger = logging.getLogger(__name__)

# === Конфигурация Redis ===
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"

# === Синхронный клиент Redis (для не-async кода) ===
sync_redis_client: Optional[Redis] = None

# === Асинхронный клиент Redis (для async кода) ===
async_redis_client: Optional[aioredis.Redis] = None


def init_sync_redis():
    """Инициализирует синхронный Redis клиент."""
    global sync_redis_client
    if not REDIS_ENABLED:
        logger.info("Redis отключён (REDIS_ENABLED=false)")
        return
    
    try:
        sync_redis_client = Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        # Проверка подключения
        sync_redis_client.ping()
        logger.info(f"Redis подключён: {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        logger.error(f"Ошибка подключения к Redis (sync): {e}")
        sync_redis_client = None


async def init_async_redis():
    """Инициализирует асинхронный Redis клиент."""
    global async_redis_client
    if not REDIS_ENABLED:
        return
    
    try:
        async_redis_client = await aioredis.from_url(
            f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        await async_redis_client.ping()
        logger.info(f"Redis подключён (async): {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        logger.error(f"Ошибка подключения к Redis (async): {e}")
        async_redis_client = None


def close_sync_redis():
    """Закрывает синхронное соединение с Redis."""
    global sync_redis_client
    if sync_redis_client:
        sync_redis_client.close()
        sync_redis_client = None


async def close_async_redis():
    """Закрывает асинхронное соединение с Redis."""
    global async_redis_client
    if async_redis_client:
        await async_redis_client.close()
        async_redis_client = None


# === Управление WebSocket соединениями через Redis ===

async def redis_add_connection(chat_id: int, user_id: int, instance_id: str) -> bool:
    """
    Добавляет WebSocket соединение в Redis.
    
    Args:
        chat_id: ID чата
        user_id: ID пользователя
        instance_id: Уникальный ID экземпляра приложения
        
    Returns:
        True если успешно (или если Redis отключён - всегда True)
    """
    if not async_redis_client:
        # Redis отключён - считаем успешным для локальной работы
        return True
    
    try:
        key = f"ws:chat:{chat_id}"
        await async_redis_client.hset(key, str(user_id), instance_id)
        await async_redis_client.expire(key, 3600)  # TTL 1 час
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления соединения в Redis: {e}")
        return False


async def redis_remove_connection(chat_id: int, user_id: int) -> bool:
    """
    Удаляет WebSocket соединение из Redis.
    
    Args:
        chat_id: ID чата
        user_id: ID пользователя
        
    Returns:
        True если успешно
    """
    if not async_redis_client:
        return False
    
    try:
        key = f"ws:chat:{chat_id}"
        await async_redis_client.hdel(key, str(user_id))
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления соединения из Redis: {e}")
        return False


async def redis_get_chat_connections(chat_id: int) -> Dict[str, str]:
    """
    Получает все соединения для чата из Redis.
    
    Args:
        chat_id: ID чата
        
    Returns:
        Dict {user_id: instance_id}
    """
    if not async_redis_client:
        return {}
    
    try:
        key = f"ws:chat:{chat_id}"
        result = await async_redis_client.hgetall(key)
        return result or {}
    except Exception as e:
        logger.error(f"Ошибка получения соединений из Redis: {e}")
        return {}


async def redis_add_user_online(user_id: int, chat_id: int) -> bool:
    """
    Добавляет пользователя в список онлайн в чате.
    
    Args:
        user_id: ID пользователя
        chat_id: ID чата
        
    Returns:
        True если успешно (или если Redis отключён - всегда True)
    """
    if not async_redis_client:
        # Redis отключён - считаем успешным
        return True
    
    try:
        key = f"online:user:{user_id}"
        await async_redis_client.sadd(key, str(chat_id))
        await async_redis_client.expire(key, 3600)
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления пользователя в онлайн: {e}")
        return False


async def redis_remove_user_online(user_id: int, chat_id: int) -> bool:
    """
    Удаляет пользователя из списка онлайн в чате.
    
    Args:
        user_id: ID пользователя
        chat_id: ID чата
        
    Returns:
        True если успешно (или если Redis отключён - всегда True)
    """
    if not async_redis_client:
        # Redis отключён - считаем успешным
        return True
    
    try:
        key = f"online:user:{user_id}"
        await async_redis_client.srem(key, str(chat_id))
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления пользователя из онлайн: {e}")
        return False


async def redis_get_user_online_chats(user_id: int) -> Set[int]:
    """
    Получает список чатов, где пользователь онлайн.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Set of chat_ids
    """
    if not async_redis_client:
        return set()
    
    try:
        key = f"online:user:{user_id}"
        result = await async_redis_client.smembers(key)
        return {int(c) for c in result} if result else set()
    except Exception as e:
        logger.error(f"Ошибка получения онлайн чатов пользователя: {e}")
        return set()


async def redis_is_user_online(user_id: int) -> bool:
    """
    Проверяет, онлайн ли пользователь (есть ли активные чаты).
    
    Args:
        user_id: ID пользователя
        
    Returns:
        True если онлайн
    """
    chats = await redis_get_user_online_chats(user_id)
    return len(chats) > 0


# === Rate Limiting для WebSocket ===

async def redis_check_ws_rate_limit(user_id: int, max_connections: int = 5) -> bool:
    """
    Проверяет лимит подключений для пользователя.
    
    Args:
        user_id: ID пользователя
        max_connections: Максимум одновременных подключений
        
    Returns:
        True если можно подключиться
    """
    if not async_redis_client:
        return True  # Если Redis отключён, пропускаем проверку
    
    try:
        key = f"ws:limit:{user_id}"
        current = await async_redis_client.get(key)
        if current is None:
            await async_redis_client.setex(key, 60, "1")
            return True
        
        if int(current) >= max_connections:
            return False
        
        await async_redis_client.incr(key)
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки rate limit: {e}")
        return True  # В случае ошибки разрешаем подключение


async def redis_increment_ws_limit(user_id: int) -> bool:
    """Увеличивает счётчик подключений пользователя."""
    if not async_redis_client:
        # Redis отключён - считаем успешным
        return True
    
    try:
        key = f"ws:limit:{user_id}"
        await async_redis_client.incr(key)
        await async_redis_client.expire(key, 60)
        return True
    except Exception as e:
        logger.error(f"Ошибка увеличения счётчика WS: {e}")
        return False


async def redis_decrement_ws_limit(user_id: int) -> bool:
    """Уменьшает счётчик подключений пользователя."""
    if not async_redis_client:
        # Redis отключён - считаем успешным
        return True
    
    try:
        key = f"ws:limit:{user_id}"
        await async_redis_client.decr(key)
        return True
    except Exception as e:
        logger.error(f"Ошибка уменьшения счётчика WS: {e}")
        return False


# === Кэширование данных ===

async def redis_cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Сохраняет значение в кэш Redis.
    
    Args:
        key: Ключ кэша
        value: Значение (будет сериализовано в JSON)
        ttl: Время жизни в секундах
        
    Returns:
        True если успешно
    """
    if not async_redis_client:
        return False
    
    try:
        await async_redis_client.setex(key, ttl, json.dumps(value))
        return True
    except Exception as e:
        logger.error(f"Ошибка записи в кэш Redis: {e}")
        return False


async def redis_cache_get(key: str) -> Optional[Any]:
    """
    Получает значение из кэша Redis.
    
    Args:
        key: Ключ кэша
        
    Returns:
        Значение или None если не найдено
    """
    if not async_redis_client:
        return None
    
    try:
        data = await async_redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.error(f"Ошибка чтения из кэша Redis: {e}")
        return None


async def redis_cache_delete(key: str) -> bool:
    """Удаляет значение из кэша."""
    if not async_redis_client:
        return False
    
    try:
        await async_redis_client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления из кэша Redis: {e}")
        return False


# === Утилиты для работы с инстансами ===

def get_instance_id() -> str:
    """Возвращает уникальный ID текущего экземпляра приложения."""
    import os
    return os.getenv("INSTANCE_ID", f"instance-{os.getpid()}")
