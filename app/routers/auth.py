import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.order import AuthSession, User, UserRole

router = APIRouter(prefix="/auth", tags=["Sessions"])


class AdminLoginRequest(BaseModel):
    access_key: str


async def _set_session(response: Response, user: User, cookie_name: str, db: AsyncSession) -> None:
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=settings.SESSION_TTL_HOURS)
    db.add(AuthSession(id=session_id, user_id=user.id, expires_at=expires_at))
    await db.commit()
    response.set_cookie(
        key=cookie_name, value=session_id,
        max_age=settings.SESSION_TTL_HOURS * 3600, httponly=True,
        secure=settings.APP_ENV != "development", samesite="lax",
    )


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT)
async def start_patron_session(
    response: Response,
    session_id: str | None = Cookie(None, alias=settings.PATRON_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    """Create an anonymous patron identity; QR data remains request context."""
    if session_id:
        existing = await db.get(AuthSession, session_id)
        if existing and existing.expires_at > datetime.utcnow():
            return
    token = secrets.token_urlsafe(16)
    user = User(name="Anonymous Patron", email=f"guest-{token}@session.local", role=UserRole.PATRON)
    db.add(user)
    await db.flush()
    await _set_session(response, user, settings.PATRON_SESSION_COOKIE_NAME, db)


@router.post("/admin/login", status_code=status.HTTP_204_NO_CONTENT)
async def admin_login(body: AdminLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    if not secrets.compare_digest(body.access_key, settings.ADMIN_ACCESS_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credential")
    admin = (await db.execute(select(User).where(User.role == UserRole.ADMIN).limit(1))).scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin account unavailable")
    await _set_session(response, admin, settings.ADMIN_SESSION_COOKIE_NAME, db)
