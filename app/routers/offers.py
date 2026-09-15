from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.auth import require_admin
from app.models.offer import Offer, OfferUsage
from app.schemas.offer import OfferCreate, OfferResponse
from app.services.offers import evaluate_offers, OfferCandidate, CartItemInput

router = APIRouter(prefix="/offers", tags=["Offers & Promotions"])

@router.get("", response_model=List[OfferResponse])
async def list_active_offers(db: AsyncSession = Depends(get_db)):
    """List all currently active promotional offers."""
    query = select(Offer).where(Offer.is_active == True).order_by(Offer.priority.desc())
    result = await db.execute(query)
    return result.scalars().all()

@router.post("", response_model=OfferResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_offer(offer_in: OfferCreate, db: AsyncSession = Depends(get_db)):
    """Admin endpoint to create a new promotional offer."""
    offer = Offer(**offer_in.model_dump())
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return offer
