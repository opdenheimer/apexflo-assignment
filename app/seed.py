import asyncio
from datetime import datetime, timedelta
from app.core.database import AsyncSessionLocal
from app.models.menu import Cinema, Screen, Show, MenuItem, Inventory
from app.models.order import User, UserRole
from app.models.offer import Offer, DiscountType

async def seed_data():
    """Seed initial minimal testing dataset with a hot low-stock item."""
    async with AsyncSessionLocal() as session:
        # Check if already seeded
        from sqlalchemy import select
        existing = await session.execute(select(Cinema).limit(1))
        if existing.scalar_one_or_none():
            print("Database already contains data, skipping seed.")
            return

        print("Seeding initial reference data...")

        # 1. Users
        patron1 = User(name="Alice Patron", email="alice@example.com", role=UserRole.PATRON)
        patron2 = User(name="Bob Patron", email="bob@example.com", role=UserRole.PATRON)
        admin = User(name="Cinema Manager", email="admin@apexflo.com", role=UserRole.ADMIN)
        session.add_all([patron1, patron2, admin])
        await session.flush()

        # 2. Cinema & Screen
        cinema = Cinema(name="ApexFlo PVR Downtown", location="Audi 1-4, Central Mall")
        session.add(cinema)
        await session.flush()

        screen1 = Screen(cinema_id=cinema.id, name="IMAX Screen 1", capacity=250)
        screen2 = Screen(cinema_id=cinema.id, name="Gold Class Screen 2", capacity=60)
        session.add_all([screen1, screen2])
        await session.flush()

        # 3. Shows
        now = datetime.utcnow()
        show1 = Show(
            movie_name="Dune: Part Two",
            cinema_id=cinema.id,
            screen_id=screen1.id,
            start_time=now - timedelta(minutes=15),
            end_time=now + timedelta(hours=2),
        )
        show2 = Show(
            movie_name="Interstellar Re-Release",
            cinema_id=cinema.id,
            screen_id=screen2.id,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3, minutes=30),
        )
        session.add_all([show1, show2])
        await session.flush()

        # 4. Menu Items
        popcorn_regular = MenuItem(
            name="Salted Butter Popcorn (Large)",
            description="Freshly popped warm golden corn with real dairy butter",
            category="Snacks",
            price=250.0,
            is_active=True,
        )
        coke_large = MenuItem(
            name="Coca-Cola Zero (650ml)",
            description="Chilled fountain soda",
            category="Beverages",
            price=150.0,
            is_active=True,
        )
        nachos_combo = MenuItem(
            name="Loaded Cheesy Nachos Combo",
            description="Crisp tortilla chips with warm jalapeño cheese dip",
            category="Combos",
            price=320.0,
            is_active=True,
        )
        # DELIBERATE HOT/LOW-STOCK ITEM FOR OVERSELL & RACE CONDITION TESTING
        caramel_special = MenuItem(
            name="Gourmet Caramel Crunch (Special Edition)",
            description="Limited small batch artisanal caramel popcorn",
            category="Snacks",
            price=380.0,
            is_active=True,
        )

        session.add_all([popcorn_regular, coke_large, nachos_combo, caramel_special])
        await session.flush()

        # 5. Inventory (Authoritative Stock)
        # Regular items: abundant stock
        # Hot item: exactly 1 unit to test race condition / oversell defense
        stock_popcorn = Inventory(
            menu_item_id=popcorn_regular.id, cinema_id=cinema.id, show_id=show1.id, quantity=100, version=0
        )
        stock_coke = Inventory(
            menu_item_id=coke_large.id, cinema_id=cinema.id, show_id=show1.id, quantity=150, version=0
        )
        stock_nachos = Inventory(
            menu_item_id=nachos_combo.id, cinema_id=cinema.id, show_id=show1.id, quantity=50, version=0
        )
        stock_caramel_contended = Inventory(
            menu_item_id=caramel_special.id, cinema_id=cinema.id, show_id=show1.id, quantity=1, version=0
        )

        session.add_all([stock_popcorn, stock_coke, stock_nachos, stock_caramel_contended])

        # 6. Tier 1 Offers (Sample configured promotions)
        offer_intermission = Offer(
            name="INTERMISSION20",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=20.0,
            priority=10,
            stackable=False,
            max_uses_per_user=1,
            is_active=True,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
        offer_flat_combo = Offer(
            name="FLAT50OFF",
            discount_type=DiscountType.FIXED,
            discount_value=50.0,
            priority=5,
            stackable=False,
            max_uses_per_user=2,
            is_active=True,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
        # Stackable offers for testing offer stacking
        offer_welcome10 = Offer(
            name="WELCOME10",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=10.0,
            priority=1,
            stackable=True,
            max_uses_per_user=3,
            is_active=True,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
        offer_flat5_stackable = Offer(
            name="FLAT5STACK",
            discount_type=DiscountType.FIXED,
            discount_value=5.0,
            priority=1,
            stackable=True,
            max_uses_per_user=5,
            is_active=True,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
        session.add_all([offer_intermission, offer_flat_combo, offer_welcome10, offer_flat5_stackable])

        await session.commit()
        print("Seed data successfully created!")

if __name__ == "__main__":
    asyncio.run(seed_data())
