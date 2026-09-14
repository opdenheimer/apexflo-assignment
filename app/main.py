import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.database import get_db, engine, Base
from app.core.redis import init_redis, close_redis, get_redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema management is intentionally startup-driven for this self-contained demo.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # The seed operation is idempotent, so a fresh Compose volume is usable immediately
    # while later restarts preserve any admin changes and orders.
    from app.seed import seed_data
    await seed_data()

    await init_redis()
    redis_client = await get_redis()
    consumer_task = asyncio.create_task(start_stock_event_consumer(redis_client))
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        await close_redis()
        await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    description="Stateless In-Cinema Food & Beverage Commerce Platform with Zero Oversell Protection",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for patron mobile browsers and admin consoles
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
from app.routers.menu import router as menu_router
from app.routers.checkout import router as checkout_router
from app.routers.orders import router as orders_router
from app.routers.offers import router as offers_router
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.realtime import router as realtime_router, start_stock_event_consumer

app.include_router(menu_router, prefix="/api")
app.include_router(checkout_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(offers_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(realtime_router)

from fastapi.staticfiles import StaticFiles
import os

# Mount Frontend static web applications
if os.path.exists("frontend/patron"):
    app.mount("/patron", StaticFiles(directory="frontend/patron", html=True), name="patron")
if os.path.exists("frontend/admin"):
    app.mount("/admin", StaticFiles(directory="frontend/admin", html=True), name="admin")

@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def healthcheck(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Core health check endpoint:
    Verifies active liveness and readiness of both PostgreSQL and Redis.
    """
    db_status = "error"
    redis_status = "error"
    
    # Check PostgreSQL
    try:
        result = await db.execute(text("SELECT 1"))
        if result.scalar() == 1:
            db_status = "ok"
    except Exception as e:
        db_status = f"unreachable: {str(e)}"

    # Check Redis
    try:
        pong = await redis.ping()
        if pong:
            redis_status = "ok"
    except Exception as e:
        redis_status = f"unreachable: {str(e)}"

    overall_healthy = (db_status == "ok") and (redis_status == "ok")

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "app": settings.APP_NAME,
        "services": {
            "postgres": db_status,
            "redis": redis_status,
        }
    }
