from datetime import datetime
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.order import AuthSession, User, UserRole


async def _get_session_user(session_id: str | None, db: AsyncSession) -> User:
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session required")
    result = await db.execute(
        select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(
            AuthSession.id == session_id, AuthSession.expires_at > datetime.utcnow()
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    return row[1]


async def require_patron(
    session_id: str | None = Cookie(None, alias=settings.PATRON_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _get_session_user(session_id, db)
    if user.role != UserRole.PATRON:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patron session required")
    return user


async def require_admin(
    session_id: str | None = Cookie(None, alias=settings.ADMIN_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _get_session_user(session_id, db)
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin session required")
    return user
