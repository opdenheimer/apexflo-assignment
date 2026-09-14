import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Enum as SQLEnum,
)
from app.core.database import Base

class DiscountType(str, enum.Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"

class Offer(Base):
    __tablename__ = "offers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    discount_type = Column(SQLEnum(DiscountType), nullable=False)
    discount_value = Column(Float, nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    stackable = Column(Boolean, default=False, nullable=False)
    max_uses_per_user = Column(Integer, default=1, nullable=False)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class OfferUsage(Base):
    __tablename__ = "offer_usage"
    id = Column(Integer, primary_key=True, index=True)
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    used_at = Column(DateTime, default=datetime.utcnow, nullable=False)

#cant have same user again applying same offer on same order
    __table_args__ = (
        UniqueConstraint("offer_id", "user_id", "order_id", name="uq_offer_user_order"),
    )
