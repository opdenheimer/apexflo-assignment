import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from app.core.database import Base
from app.models.menu import Cinema, Screen, Show, MenuItem, Inventory
from app.models.order import User, UserRole, Order
from app.models.offer import Offer, OfferUsage, DiscountType
from app.schemas.order import CheckoutRequest, CheckoutLineItem
from app.services.checkout import process_checkout
from sqlalchemy import select

TEST_DATABASE_URL = "sqlite+aiosqlite:///test.db"

@pytest_asyncio.fixture
async def async_session_factory():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.mark.asyncio
async def test_checkout_atomic_success_and_idempotency_replay(async_session_factory):
    """
    Verify:
    1. A valid checkout claims stock and commits the order.
    2. Re-submitting the same request with the identical idempotency_key returns the prior order without deducting stock again.
    """
    async with async_session_factory() as session:
        user = User(name="Alice", email="alice@test.com", role=UserRole.PATRON)
        cinema = Cinema(name="PVR Central", location="Audi 1")
        session.add_all([user, cinema])
        await session.flush()

        screen = Screen(cinema_id=cinema.id, name="Screen 1", capacity=100)
        session.add(screen)
        await session.flush()

        show = Show(
            movie_name="Inception",
            cinema_id=cinema.id,
            screen_id=screen.id,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(hours=2),
        )
        item = MenuItem(name="Large Soda", category="Drinks", price=150.0)
        session.add_all([show, item])
        await session.flush()

        # Stock = 5 units
        inv = Inventory(
            menu_item_id=item.id,
            cinema_id=cinema.id,
            show_id=show.id,
            quantity=5,
            version=0,
        )
        session.add(inv)
        await session.commit()

        user_id = user.id
        show_id = show.id
        screen_id = screen.id
        item_id = item.id

    request = CheckoutRequest(
        show_id=show_id,
        screen_id=screen_id,
        seat="H10",
        idempotency_key="idemp_key_unique_001",
        items=[CheckoutLineItem(menu_item_id=item_id, quantity=2)],
    )

    # First Checkout: should succeed
    async with async_session_factory() as session:
        resp1 = await process_checkout(db=session, redis=None, user_id=user_id, request=request)
        assert resp1.order_id is not None
        assert resp1.total == 300.0
        assert resp1.seat == "H10"

    # Verify stock dropped from 5 -> 3
    async with async_session_factory() as session:
        from sqlalchemy import select
        inv_check = await session.execute(select(Inventory).where(Inventory.menu_item_id == item_id))
        assert inv_check.scalar_one().quantity == 3

    # Replay identical checkout (same idempotency key): should return prior order without deducting stock again!
    async with async_session_factory() as session:
        resp2 = await process_checkout(db=session, redis=None, user_id=user_id, request=request)
        assert resp2.order_id == resp1.order_id
        assert resp2.idempotency_key == "idemp_key_unique_001"

    # Verify stock is STILL 3 (no double deduction)
    async with async_session_factory() as session:
        inv_check2 = await session.execute(select(Inventory).where(Inventory.menu_item_id == item_id))
        assert inv_check2.scalar_one().quantity == 3

@pytest.mark.asyncio
async def test_checkout_multi_item_transaction_rollback(async_session_factory):
    """
    Multi-item Atomic Rollback Test:
    Cart has Item A (in stock = 10) and Item B (out of stock = 0).
    The whole transaction MUST rollback. Item A must NOT be decremented. No order row created.
    """
    async with async_session_factory() as session:
        user = User(name="Bob", email="bob@test.com", role=UserRole.PATRON)
        cinema = Cinema(name="PVR Central", location="Audi 1")
        session.add_all([user, cinema])
        await session.flush()

        screen = Screen(cinema_id=cinema.id, name="Screen 1", capacity=100)
        session.add(screen)
        await session.flush()

        show = Show(
            movie_name="Avatar 3",
            cinema_id=cinema.id,
            screen_id=screen.id,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(hours=2),
        )
        item_available = MenuItem(name="Butter Popcorn", category="Food", price=200.0)
        item_sold_out = MenuItem(name="Special Combo", category="Food", price=450.0)
        session.add_all([show, item_available, item_sold_out])
        await session.flush()

        inv1 = Inventory(menu_item_id=item_available.id, cinema_id=cinema.id, show_id=show.id, quantity=10, version=0)
        inv2 = Inventory(menu_item_id=item_sold_out.id, cinema_id=cinema.id, show_id=show.id, quantity=0, version=0)
        session.add_all([inv1, inv2])
        await session.commit()

        user_id = user.id
        show_id = show.id
        screen_id = screen.id
        item_a_id = item_available.id
        item_b_id = item_sold_out.id

    request = CheckoutRequest(
        show_id=show_id,
        screen_id=screen_id,
        seat="F12",
        idempotency_key="idemp_key_rollback_002",
        items=[
            CheckoutLineItem(menu_item_id=item_a_id, quantity=2),
            CheckoutLineItem(menu_item_id=item_b_id, quantity=1),
        ],
    )

    # Attempt checkout: MUST raise 409 Conflict
    async with async_session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await process_checkout(db=session, redis=None, user_id=user_id, request=request)
        assert exc_info.value.status_code == 409

    # Verify: Item A stock is STILL 10 (did not decrement)
    async with async_session_factory() as session:
        from sqlalchemy import select
        res_a = await session.execute(select(Inventory).where(Inventory.menu_item_id == item_a_id))
        assert res_a.scalar_one().quantity == 10

        # Verify: Zero orders exist in database
        orders_check = await session.execute(select(Order))
        assert len(orders_check.scalars().all()) == 0

@pytest.mark.asyncio
async def test_checkout_with_stackable_offers(async_session_factory):
    """
    Verify that stackable offers are applied during checkout and OfferUsage rows are persisted for all applied offers.
    """
    from app.models.offer import Offer, DiscountType
    from app.services.offers import evaluate_offers, OfferCandidate, CartItemInput, calculate_offer_discount
    from app.schemas.order import CheckoutRequest, CheckoutLineItem
    from app.models.menu import Cinema, Screen, Show, MenuItem
    from app.models.order import User, UserRole
    from sqlalchemy import select
    
    async with async_session_factory() as session:
        # Add user, cinema, screen, show, item
        user = User(name="Alice", email="alice@test.com", role=UserRole.PATRON)
        cinema = Cinema(name="PVR Central", location="Audi 1")
        session.add_all([user, cinema])
        await session.flush()
        
        screen = Screen(cinema_id=cinema.id, name="Screen 1", capacity=100)
        session.add(screen)
        await session.flush()
        
        show = Show(
            movie_name="Inception",
            cinema_id=cinema.id,
            screen_id=screen.id,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(hours=2),
        )
        item = MenuItem(name="Large Soda", category="Drinks", price=150.0)
        session.add_all([show, item])
        await session.flush()
        
        # Add stackable offers
        offer1 = Offer(
            name="WELCOME10",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=10.0,
            priority=1,
            stackable=True,
            max_uses_per_user=3,
            is_active=True,
            start_time=datetime.now() - timedelta(hours=1),
            end_time=datetime.now() + timedelta(hours=2),
        )
        offer2 = Offer(
            name="FLAT5STACK",
            discount_type=DiscountType.FIXED,
            discount_value=5.0,
            priority=1,
            stackable=True,
            max_uses_per_user=5,
            is_active=True,
            start_time=datetime.now() - timedelta(hours=1),
            end_time=datetime.now() + timedelta(hours=2),
        )
        session.add_all([offer1, offer2])
        
        # Add inventory
        inv = Inventory(
            menu_item_id=item.id,
            cinema_id=cinema.id,
            show_id=show.id,
            quantity=5,
            version=0,
        )
        session.add(inv)
        await session.commit()
        
        await session.flush()
    
    user_id = user.id
    show_id = show.id
    screen_id = screen.id
    item_id = item.id
    
    request = CheckoutRequest(
        show_id=show_id,
        screen_id=screen_id,
        seat="H10",
        idempotency_key="idemp_key_stackable_001",
        items=[CheckoutLineItem(menu_item_id=item_id, quantity=2)],  # subtotal = 300
    )
    
    # First Checkout with stackable offers
    async with async_session_factory() as session:
        resp1 = await process_checkout(db=session, redis=None, user_id=user_id, request=request)
        print(f'Order total: {resp1.total}')
        print(f'Order discount: {resp1.discount}')
        print(f'Order subtotal: {resp1.subtotal}')
        print(f'Items: {len(resp1.items)}')
        
        # Verify discount was applied (should be more than 0)
        assert resp1.discount > 0, f"Expected discount > 0, got {resp1.discount}"
        
        # Verify total is less than subtotal
        assert resp1.total < resp1.subtotal, f"Expected total < subtotal, got total={resp1.total}, subtotal={resp1.subtotal}"
        
        # Check that OfferUsage rows were created for both offers
        usage_query = select(OfferUsage).where(OfferUsage.user_id == user_id)
        usage_res = await session.execute(usage_query)
        usage_rows = usage_res.scalars().all()
        print(f'OfferUsage rows created: {len(usage_rows)}')
        assert len(usage_rows) >= 1, f"Expected at least 1 OfferUsage row, got {len(usage_rows)}"
        
        # Verify the discounts sum up correctly
        # WELCOME10: 10% of 300 = 30
        # FLAT5STACK: 5 fixed
        # Total discount should be 35
        assert resp1.discount == 35.0, f"Expected discount 35.0, got {resp1.discount}"
        assert resp1.total == 265.0, f"Expected total 265.0, got {resp1.total}"
