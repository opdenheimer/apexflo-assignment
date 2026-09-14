import json
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as aioredis

from app.models.menu import Show, Cinema, Screen, MenuItem, Inventory
from app.schemas.menu import MenuResponse, MenuItemResponse

logger = logging.getLogger(__name__)
MENU_CACHE_TTL_SECONDS = 30

async def get_menu_for_show(
    show_id: int,
    db: AsyncSession,
    redis: Optional[aioredis.Redis] = None,
) -> Optional[MenuResponse]:
    """
    Retrieve menu for a given show:
    1. Read through Redis cache `menu:show:{show_id}`.
    2. On miss/failure, fallback to PostgreSQL.
    3. Filter/flag sold-out items.
    """
    cache_key = f"menu:show:{show_id}"

    # Step 1: Redis Read
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return MenuResponse.model_validate_json(cached)
        except Exception as e:
            logger.warning(f"Redis cache read error, falling back to DB: {e}")

    # Step 2: Database Fallback
    show = await db.get(Show, show_id)
    if not show:
        return None

    cinema = await db.get(Cinema, show.cinema_id)
    screen = await db.get(Screen, show.screen_id)

    inv_query = (
        select(MenuItem, Inventory.quantity)
        .outerjoin(
            Inventory,
            (Inventory.menu_item_id == MenuItem.id) & (Inventory.show_id == show_id)
        )
        .where(MenuItem.is_active == True)
    )
    inv_result = await db.execute(inv_query)
    rows = inv_result.all()

    menu_items = []
    for item, quantity in rows:
        qty = quantity if quantity is not None else 0
        menu_items.append(
            MenuItemResponse(
                id=item.id,
                name=item.name,
                description=item.description,
                category=item.category,
                price=item.price,
                is_active=item.is_active,
                available_stock=qty,
                is_available=(qty > 0 and item.is_active),
            )
        )

    response = MenuResponse(
        show_id=show.id,
        movie_name=show.movie_name,
        cinema_name=cinema.name if cinema else "Cinema",
        screen_name=screen.name if screen else "Screen",
        items=menu_items,
    )

    # Step 3: Populate Redis cache
    if redis:
        try:
            await redis.set(cache_key, response.model_dump_json(), ex=MENU_CACHE_TTL_SECONDS)
        except Exception as e:
            logger.warning(f"Failed to populate Redis cache: {e}")

    return response
