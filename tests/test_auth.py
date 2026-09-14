from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import require_admin, require_patron
from app.core.database import Base
from app.models.order import AuthSession, User, UserRole


@pytest_asyncio.fixture
async def auth_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_patron_session_cannot_be_used_as_admin(auth_db):
    patron = User(name="Guest", email="guest@test.local", role=UserRole.PATRON)
    auth_db.add(patron)
    await auth_db.flush()
    auth_db.add(AuthSession(id="guest-session", user_id=patron.id, expires_at=datetime.utcnow() + timedelta(hours=1)))
    await auth_db.commit()

    assert (await require_patron("guest-session", auth_db)).id == patron.id
    with pytest.raises(HTTPException) as error:
        await require_admin("guest-session", auth_db)
    assert error.value.status_code == 403
