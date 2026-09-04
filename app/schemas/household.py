from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class HouseholdBase(BaseModel):
    household_name: str
    busy_days: List[str] = ["Tuesday", "Thursday"]
    busy_max_prep_minutes: int = 20

class HouseholdCreate(HouseholdBase):
    dietary_preferences: Optional[List[str]] = []
    busy_days: Optional[List[str]] = ["Tuesday", "Thursday"]
    busy_max_prep_minutes: Optional[int] = 20

class HouseholdUpdate(BaseModel):
    household_name: Optional[str] = None
    dietary_preferences: Optional[List[str]] = None
    busy_days: Optional[List[str]] = None
    busy_max_prep_minutes: Optional[int] = None

class HouseholdScheduleUpdateRequest(BaseModel):
    busy_days: List[str] = ["Tuesday", "Thursday"]
    busy_max_prep_minutes: int = 20

class HouseholdResponse(HouseholdBase):
    household_id: UUID
    dietary_preferences: List[str] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class HouseholdDietaryUpdateRequest(BaseModel):
    dietary_preferences: List[str]
