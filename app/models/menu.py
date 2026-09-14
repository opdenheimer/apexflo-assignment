from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Text,
)
from app.core.database import Base

class Cinema(Base):
    __tablename__ = "cinemas"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    location = Column(String(200), nullable=False)

class Screen(Base):
    __tablename__ = "screens"
    id = Column(Integer, primary_key=True, index=True)
    cinema_id = Column(Integer, ForeignKey("cinemas.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(50), nullable=False)
    capacity = Column(Integer, nullable=False)

class Show(Base):
    __tablename__ = "shows"
    id = Column(Integer, primary_key=True, index=True)
    movie_name = Column(String(150), nullable=False)
    cinema_id = Column(Integer, ForeignKey("cinemas.id", ondelete="CASCADE"), nullable=False)
    screen_id = Column(Integer, ForeignKey("screens.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)

class MenuItem(Base):
    __tablename__ = "menu_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    category = Column(String(50), nullable=False)
    price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"), nullable=False)
    cinema_id = Column(Integer, ForeignKey("cinemas.id", ondelete="CASCADE"), nullable=False)
    show_id = Column(Integer, ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False)
    version = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="check_inventory_quantity_non_negative"),
        UniqueConstraint("menu_item_id", "cinema_id", "show_id", name="uq_item_cinema_show"),
    )
