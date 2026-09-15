import logging
import json
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
import redis.asyncio as aioredis

from app.models.menu import Show, MenuItem
from app.models.order import Order, OrderItem, OrderStatus, User
from app.schemas.order import CheckoutRequest, CheckoutResponse, CartItemResponse
from app.services.inventory import claim_stock

logger = logging.getLogger(__name__)

async def process_checkout(
    db: AsyncSession,
    redis: aioredis.Redis,
    user_id: int,
    request: CheckoutRequest,
) -> CheckoutResponse:
    """
    8-Step Transactional Checkout Orchestration (Phase 4):
    
    1. Idempotency Check: Short-circuit if idempotency_key already processed.
    2. Show & Context Validation: Ensure show and user exist.
    3. Item Deadlock Prevention: Sort line items deterministically by menu_item_id.
    4. Atomic Stock Claims: Decrement each item via single SQL conditional statement.
    5. Rollback on Failure: If any item fails claim, rollback whole transaction.
    6. Persist Order: Insert Order + OrderItems within the same atomic transaction.
    7. Commit Transaction.
    8. Post-Commit Event Publish: Emit StockChanged events to Redis Streams.
    """
    # -------------------------------------------------------------
    # Step 1: Idempotency Check
    # -------------------------------------------------------------
    existing_order_query = select(Order).where(Order.idempotency_key == request.idempotency_key)
    existing_order_result = await db.execute(existing_order_query)
    existing_order = existing_order_result.scalar_one_or_none()

    if existing_order:
        logger.info(f"Duplicate checkout request detected for idempotency_key={request.idempotency_key}. Returning prior result.")
        # Load order items to return identical response
        items_query = select(OrderItem, MenuItem.name).join(MenuItem, MenuItem.id == OrderItem.menu_item_id).where(OrderItem.order_id == existing_order.id)
        items_result = await db.execute(items_query)
        cached_items = [
            CartItemResponse(
                menu_item_id=oi.menu_item_id,
                name=name,
                unit_price=oi.unit_price,
                quantity=oi.quantity,
                total_price=oi.unit_price * oi.quantity - oi.discount,
            )
            for oi, name in items_result.all()
        ]
        return CheckoutResponse(
            order_id=existing_order.id,
            status=existing_order.status.value,
            seat=existing_order.seat,
            subtotal=existing_order.subtotal,
            discount=existing_order.discount,
            total=existing_order.total,
            idempotency_key=existing_order.idempotency_key,
            items=cached_items,
            created_at=existing_order.created_at,
        )

    # -------------------------------------------------------------
    # Step 2: Validate Show & Cinema context
    # -------------------------------------------------------------
    show = await db.get(Show, request.show_id)
    if not show:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Show not found")
    cinema_id = show.cinema_id

    # -------------------------------------------------------------
    # Step 3: Sort items by ID to prevent deadlocks under high concurrency
    # -------------------------------------------------------------
    sorted_items = sorted(request.items, key=lambda x: x.menu_item_id)

    # -------------------------------------------------------------
    # Step 4: Evaluate Tier 1 Offers BEFORE Stock Claim
    # -------------------------------------------------------------
    # Load active offers from DB
    from app.models.offer import Offer, OfferUsage
    from app.services.offers import evaluate_offers, OfferCandidate, CartItemInput, calculate_offer_discount

    active_offers_query = select(Offer).where(Offer.is_active == True)
    active_offers_res = await db.execute(active_offers_query)
    db_offers = active_offers_res.scalars().all()

    # Load user's past offer redemptions
    usage_query = select(OfferUsage.offer_id).where(OfferUsage.user_id == user_id)
    usage_res = await db.execute(usage_query)
    user_usage_counts = {}
    for (o_id,) in usage_res.all():
        user_usage_counts[o_id] = user_usage_counts.get(o_id, 0) + 1

    # Prepare cart input for pure evaluation engine
    # Collect items & prices first
    item_lookup = {}
    for item_req in sorted_items:
        m_item = await db.get(MenuItem, item_req.menu_item_id)
        if not m_item or not m_item.is_active:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Menu item {item_req.menu_item_id} is inactive or does not exist",
            )
        item_lookup[item_req.menu_item_id] = m_item

    cart_inputs = [
        CartItemInput(
            menu_item_id=req.menu_item_id,
            unit_price=item_lookup[req.menu_item_id].price,
            quantity=req.quantity,
        )
        for req in sorted_items
    ]

    offer_candidates = [
        OfferCandidate(
            id=o.id,
            name=o.name,
            discount_type=o.discount_type,
            discount_value=o.discount_value,
            priority=o.priority,
            stackable=o.stackable,
            max_uses_per_user=o.max_uses_per_user,
            start_time=o.start_time,
            end_time=o.end_time,
            is_active=o.is_active,
        )
        for o in db_offers
    ]

    # -------------------------------------------------------------
    # Step 4: Evaluate Offers (primary)
    # -------------------------------------------------------------
    # Offer evaluation will be performed after subtotal is calculated (see later block)

    # -------------------------------------------------------------
    # Step 5: Atomic Stock Claims inside DB Transaction
    # -------------------------------------------------------------
    claimed_stock_events = []
    line_item_snapshots = []
    subtotal = 0.0

    for item_req in sorted_items:
        menu_item = item_lookup[item_req.menu_item_id]
        item_name = menu_item.name
        item_price = menu_item.price

        # Atomic conditional decrement
        success, new_qty, new_version = await claim_stock(
            db=db,
            menu_item_id=item_req.menu_item_id,
            cinema_id=cinema_id,
            show_id=request.show_id,
            quantity=item_req.quantity,
        )

        if not success:
            # Atomic claim failed: out of stock or contended
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Item '{item_name}' is out of stock or insufficient quantity",
            )

        # Track event for post-commit publishing
        claimed_stock_events.append({
            "menu_item_id": item_req.menu_item_id,
            "cinema_id": cinema_id,
            "show_id": request.show_id,
            "new_quantity": new_qty,
            "version": new_version,
        })

        item_total = item_price * item_req.quantity
        subtotal += item_total
        line_item_snapshots.append((item_req.menu_item_id, item_name, item_price, item_req.quantity, item_total))
    # -------------------------------------------------------------
    # Step 5: Evaluate Offers (including stackable)
    # -------------------------------------------------------------
    # If patron explicitly requested an offer_code, filter or prioritize it
    candidates_to_eval = offer_candidates
    if request.offer_code:
        matching = [o for o in offer_candidates if o.name.strip().upper() == request.offer_code.strip().upper()]
        if matching:
            # If specified by user, put matching offer first with boosted priority so it evaluates primarily
            candidates_to_eval = matching + [o for o in offer_candidates if o.id != matching[0].id]

    # Evaluate primary offer
    offer_result = evaluate_offers(
        items=cart_inputs,
        active_offers=candidates_to_eval,
        user_usage_counts=user_usage_counts,
    )
    discount = offer_result.discount_amount
    applied_offer = offer_result.applied_offer
    applied_offers = [applied_offer] if applied_offer else []

    # Handle stackable offers: sort by priority desc, then id asc (earlier offer first)
    stackable_candidates = sorted(
        [o for o in offer_candidates if o.stackable and (not applied_offer or o.id != applied_offer.id)],
        key=lambda x: (-x.priority, x.id)
    )

    stackable_offers = []
    additional_discount = 0.0
    if applied_offer and applied_offer.stackable:
        for offer in stackable_candidates:
            now = datetime.now()
            if not offer.is_active:
                continue
            if offer.start_time and now < offer.start_time:
                continue
            if offer.end_time and now > offer.end_time:
                continue
            used = user_usage_counts.get(offer.id, 0)
            if used >= offer.max_uses_per_user:
                continue
            disc = calculate_offer_discount(offer, subtotal)
            if disc > 0:
                additional_discount += disc
                stackable_offers.append(offer)
                applied_offers.append(offer)
    discount += additional_discount

    # -------------------------------------------------------------
    # Step 6: Persist Order, OrderItems, and OfferUsage in one transaction
    # -------------------------------------------------------------
    total = max(0.0, round(subtotal - discount, 2))

    new_order = Order(
        user_id=user_id,
        show_id=request.show_id,
        screen_id=request.screen_id,
        seat=request.seat,
        status=OrderStatus.PLACED,
        subtotal=subtotal,
        discount=discount,
        total=total,
        idempotency_key=request.idempotency_key,
    )
    db.add(new_order)
    await db.flush()  # Populates new_order.id

    for offer in applied_offers:
        db.add(OfferUsage(
            offer_id=offer.id,
            user_id=user_id,
            order_id=new_order.id,
            used_at=datetime.utcnow(),
        ))

    order_item_records = []
    response_items = []
    for m_id, m_name, m_price, qty, line_total in line_item_snapshots:
        db.add(OrderItem(
            order_id=new_order.id,
            menu_item_id=m_id,
            quantity=qty,
            unit_price=m_price,
            discount=0.0,
        ))
        response_items.append(
            CartItemResponse(
                menu_item_id=m_id,
                name=m_name,
                unit_price=m_price,
                quantity=qty,
                total_price=line_total,
            )
        )

    # Step 7: Commit Transaction
    await db.commit()
    await db.refresh(new_order)

    # -------------------------------------------------------------
    # Step 8: Post-Commit Event Publish (Never hold DB locks for Redis)
    # -------------------------------------------------------------
    if redis:
        try:
            for event in claimed_stock_events:
                # Update Redis projection key: stock:{show_id}:{menu_item_id}
                proj_key = f"stock:{event['show_id']}:{event['menu_item_id']}"
                await redis.set(proj_key, json.dumps({
                    "quantity": event["new_quantity"],
                    "version": event["version"],
                }))

                # Invalidate menu cache so subsequent reads see latest stock projection
                await redis.delete(f"menu:show:{event['show_id']}")

                # Publish StockChanged event to Redis Streams
                await redis.xadd(
                    "stock-events",
                    {
                        "event_type": "StockChanged",
                        "menu_item_id": str(event["menu_item_id"]),
                        "show_id": str(event["show_id"]),
                        "cinema_id": str(event["cinema_id"]),
                        "new_quantity": str(event["new_quantity"]),
                        "version": str(event["version"]),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
        except Exception as e:
            # Non-blocking: Order is already safely committed in DB source of truth
            logger.error(f"Post-commit Redis event publish failed (will be reconciled): {e}")

    return CheckoutResponse(
        order_id=new_order.id,
        status=new_order.status.value,
        seat=new_order.seat,
        subtotal=new_order.subtotal,
        discount=new_order.discount,
        total=new_order.total,
        idempotency_key=new_order.idempotency_key,
        items=response_items,
        created_at=new_order.created_at,
    )
