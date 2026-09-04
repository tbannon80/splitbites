from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class PantryItemCreate(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=100)
    is_in_stock: bool = True

class PantryItemUpdate(BaseModel):
    item_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_in_stock: Optional[bool] = None

class PantryItemResponse(BaseModel):
    pantry_id: UUID
    household_id: UUID
    item_name: str
    is_in_stock: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
