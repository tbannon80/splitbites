from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    user_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

from app.schemas.household import (
    HouseholdBase,
    HouseholdCreate,
    HouseholdUpdate,
    HouseholdScheduleUpdateRequest,
    HouseholdResponse,
    HouseholdDietaryUpdateRequest,
)

class UserProfileScaffold(BaseModel):
    user: UserResponse
    households: List[HouseholdResponse] = []
    dietary_preferences: List[str] = []
