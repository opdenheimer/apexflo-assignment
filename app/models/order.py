import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
)
from app.core.database import Base

class OrderStatus(str, enum.Enum):
    PLACED = "PLACED"
    PREPARING = "PREPARING"
    READY = "READY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"

class UserRole(str, enum.Enum):
    PATRON = "PATRON"
    ADMIN = "ADMIN"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.PATRON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class Cart(Base):
    __tablename__ = "carts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    show_id = Column(Integer, ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    show_id = Column(Integer, ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    screen_id = Column(Integer, ForeignKey("screens.id", ondelete="CASCADE"), nullable=False)
    seat = Column(String(20), nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PLACED, nullable=False)
    subtotal = Column(Float, nullable=False)
    discount = Column(Float, default=0.0, nullable=False)
    total = Column(Float, nullable=False)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    discount = Column(Float, default=0.0, nullable=False)
