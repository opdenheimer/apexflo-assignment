import logging
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

async def claim_stock(
    db: AsyncSession,
    menu_item_id: int,
    cinema_id: int,
    show_id: int,
    quantity: int = 1,
) -> Tuple[bool, Optional[int], Optional[int]]:
    """
    Atomic Stock Claim (Core Correctness).
    Executes a single conditional UPDATE statement:
    - Atomically checks if available quantity >= requested quantity.
    - Decrements quantity and increments version in the same atomic operation.
    - If 0 rows affected: out of stock / contention. Returns (False, None, None).
    - If 1 row affected: claim succeeded. Returns (True, new_quantity, new_version).
    """
    sql = text("""
        UPDATE inventory
        SET quantity = quantity - :qty,
            version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE menu_item_id = :item_id
          AND cinema_id = :cinema_id
          AND show_id = :show_id
          AND quantity >= :qty
        RETURNING quantity, version;
    """)

    result = await db.execute(
        sql,
        {
            "qty": quantity,
            "item_id": menu_item_id,
            "cinema_id": cinema_id,
            "show_id": show_id,
        },
    )
    row = result.fetchone()

    if row is None:
        return False, None, None

    new_qty, new_version = row[0], row[1]
    return True, new_qty, new_version
