import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from app.core.database import Base
from app.models.menu import Cinema, Screen, Show, MenuItem, Inventory
from app.models.order import Order, OrderStatus, User, UserRole

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def async_db():
    """Isolated in-memory SQLite database enforcing constraints for fast testing."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    # Enable foreign keys and check constraints in SQLite
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.mark.asyncio
async def test_inventory_check_constraint_prevents_negative_quantity(async_db: AsyncSession):
    """
    Test Phase 1 Schema Correctness:
    Verifies that the CHECK (quantity >= 0) constraint prevents negative stock at the database level.
    """
    cinema = Cinema(name="Test Cinema", location="Downtown")
    async_db.add(cinema)
    await async_db.flush()

    screen = Screen(cinema_id=cinema.id, name="Screen 1", capacity=100)
    async_db.add(screen)
    await async_db.flush()

    from datetime import datetime, timedelta
    show = Show(
        movie_name="Test Movie",
        cinema_id=cinema.id,
        screen_id=screen.id,
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow() + timedelta(hours=2),
    )
    item = MenuItem(name="Popcorn", category="Snack", price=100.0)
    async_db.add_all([show, item])
    await async_db.flush()

    # Create inventory with valid stock = 5
    inv = Inventory(
        menu_item_id=item.id,
        cinema_id=cinema.id,
        show_id=show.id,
        quantity=5,
        version=0,
    )
    async_db.add(inv)
    await async_db.commit()

    # Attempt to illegally set negative quantity
    inv.quantity = -1
    with pytest.raises(IntegrityError):
        await async_db.commit()
    await async_db.rollback()

@pytest.mark.asyncio
async def test_order_idempotency_key_uniqueness(async_db: AsyncSession):
    """
    Test Phase 1 Schema Correctness:
    Verifies that UNIQUE(idempotency_key) prevents duplicate orders at the database level.
    """
    user = User(name="Test User", email="test@example.com", role=UserRole.PATRON)
    cinema = Cinema(name="Test Cinema", location="Downtown")
    async_db.add_all([user, cinema])
    await async_db.flush()

    screen = Screen(cinema_id=cinema.id, name="Screen 1", capacity=100)
    async_db.add(screen)
    await async_db.flush()

    from datetime import datetime, timedelta
    show = Show(
        movie_name="Test Movie",
        cinema_id=cinema.id,
        screen_id=screen.id,
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow() + timedelta(hours=2),
    )
    async_db.add(show)
    await async_db.flush()

    # First order with idempotency key "order_key_123"
    order1 = Order(
        user_id=user.id,
        show_id=show.id,
        screen_id=screen.id,
        seat="K12",
        status=OrderStatus.PLACED,
        subtotal=200.0,
        discount=0.0,
        total=200.0,
        idempotency_key="order_key_123",
    )
    async_db.add(order1)
    await async_db.commit()

    # Duplicate order with identical idempotency key must fail
    order2 = Order(
        user_id=user.id,
        show_id=show.id,
        screen_id=screen.id,
        seat="K12",
        status=OrderStatus.PLACED,
        subtotal=200.0,
        discount=0.0,
        total=200.0,
        idempotency_key="order_key_123",
    )
    async_db.add(order2)
    with pytest.raises(IntegrityError):
        await async_db.commit()
    await async_db.rollback()
