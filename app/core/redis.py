from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings

redis_client: Optional[aioredis.Redis] = None

async def init_redis() -> aioredis.Redis:
    """Initialize the global async Redis connection pool."""
    global redis_client
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
    )
    return redis_client

async def get_redis() -> aioredis.Redis:
    """FastAPI dependency to retrieve the active Redis client."""
    global redis_client
    if redis_client is None:
        redis_client = await init_redis()
    return redis_client

async def close_redis() -> None:
    """Gracefully close the Redis connection pool on app shutdown."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
