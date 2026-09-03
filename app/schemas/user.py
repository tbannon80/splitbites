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

class HouseholdBase(BaseModel):
    household_name: str

class HouseholdCreate(HouseholdBase):
    dietary_preferences: Optional[List[str]] = []

class HouseholdResponse(HouseholdBase):
    household_id: UUID
    dietary_preferences: List[str] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class HouseholdDietaryUpdateRequest(BaseModel):
    dietary_preferences: List[str]

class UserProfileScaffold(BaseModel):
    user: UserResponse
    households: List[HouseholdResponse] = []
    dietary_preferences: List[str] = []
