from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.models.offer import DiscountType

class OfferCreate(BaseModel):
    name: str
    discount_type: DiscountType
    discount_value: float = Field(gt=0)
    priority: int = 0
    stackable: bool = False
    max_uses_per_user: int = 1
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_active: bool = True

class OfferResponse(BaseModel):
    id: int
    name: str
    discount_type: DiscountType
    discount_value: float
    priority: int
    stackable: bool
    max_uses_per_user: int
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True
