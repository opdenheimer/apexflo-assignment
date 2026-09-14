from pydantic import BaseModel, Field
from typing import List, Optional

class MenuItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = ""
    category: str
    price: float
    is_active: bool
    available_stock: int = Field(default=0, description="Projected live stock")
    is_available: bool = Field(default=True, description="False if stock <= 0 or inactive")

    class Config:
        from_attributes = True

class MenuResponse(BaseModel):
    show_id: int
    movie_name: str
    cinema_name: str
    screen_name: str
    items: List[MenuItemResponse]
