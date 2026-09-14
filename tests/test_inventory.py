import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from app.core.database import Base
from app.models.menu import Cinema, Screen, Show, MenuItem, Inventory
from app.services.inventory import claim_stock

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
async def async_session_factory():
    """Create a fresh shared test engine and sessionmaker."""
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
async def test_atomic_stock_claim_success_and_depletion(async_session_factory):
    """
    Test that a single claim succeeds and correctly decrements quantity and bumps version.
    """
    async with async_session_factory() as session:
        cinema = Cinema(name="Test Cinema", location="Downtown")
        session.add(cinema)
        await session.flush()

        screen = Screen(cinema_id=cinema.id, name="Screen 1", capacity=100)
        session.add(screen)
        await session.flush()

        show = Show(
            movie_name="Test Movie",
            cinema_id=cinema.id,
            screen_id=screen.id,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(hours=2),
        )
        item = MenuItem(name="Caramel Popcorn", category="Snack", price=250.0)
        session.add_all([show, item])
        await session.flush()

        # Seed 1 single unit of stock
        inv = Inventory(
            menu_item_id=item.id,
            cinema_id=cinema.id,
            show_id=show.id,
            quantity=1,
            version=0,
        )
        session.add(inv)
        await session.commit()

        item_id = item.id
        cinema_id = cinema.id
        show_id = show.id

    # 1. First claim: request 1 unit -> must SUCCEED
    async with async_session_factory() as session:
        success, new_qty, new_version = await claim_stock(session, item_id, cinema_id, show_id, quantity=1)
        await session.commit()
        assert success is True
        assert new_qty == 0
        assert new_version == 1

    # 2. Second claim: stock is now 0 -> must FAIL
    async with async_session_factory() as session:
        success, new_qty, new_version = await claim_stock(session, item_id, cinema_id, show_id, quantity=1)
        await session.commit()
        assert success is False
        assert new_qty is None

@pytest.mark.asyncio
async def test_concurrent_claims_on_contended_item(async_session_factory):
    """
    The Single Most Important Test in the Assignment:
    Spawn 20 parallel transactions all attempting to claim the final unit of stock (quantity=1).
    EXACTLY ONE must succeed; ALL other 19 must fail cleanly with zero oversell.
    """
    async with async_session_factory() as session:
        cinema = Cinema(name="Test Cinema", location="Downtown")
        session.add(cinema)
        await session.flush()

        screen = Screen(cinema_id=cinema.id, name="Screen 1", capacity=100)
        session.add(screen)
        await session.flush()

        show = Show(
            movie_name="Blockbuster Hit",
            cinema_id=cinema.id,
            screen_id=screen.id,
            start_time=datetime.now(),
            end_time=datetime.now() + timedelta(hours=2),
        )
        item = MenuItem(name="Limited Edition Popcorn Bucket", category="Snacks", price=500.0)
        session.add_all([show, item])
        await session.flush()

        # Exactly 1 unit available
        inv = Inventory(
            menu_item_id=item.id,
            cinema_id=cinema.id,
            show_id=show.id,
            quantity=1,
            version=0,
        )
        session.add(inv)
        await session.commit()

        item_id, cinema_id, show_id = item.id, cinema.id, show.id

    async def attempt_claim():
        async with async_session_factory() as session:
            success, qty, ver = await claim_stock(session, item_id, cinema_id, show_id, quantity=1)
            if success:
                await session.commit()
            else:
                await session.rollback()
            return success

    # Fire 20 parallel concurrent claim requests simultaneously
    results = await asyncio.gather(*(attempt_claim() for _ in range(20)))

    successes = [r for r in results if r is True]
    failures = [r for r in results if r is False]

    # PROOF OF ZERO OVERSELL:
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 19, f"Expected 19 failures, got {len(failures)}"
