from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict
from uuid import UUID
from datetime import date

class MealPlanGenerateRequest(BaseModel):
    household_id: Optional[UUID] = None
    target_date: Optional[date] = None
    dietary_tags: Optional[List[str]] = None
    days_count: int = 5

class MealSlotResponse(BaseModel):
    recipe_id: str
    title: str
    description: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    difficulty_level: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class WeeklyMealPlanResponse(BaseModel):
    status: str
    plan_type: str
    meals: Dict[str, MealSlotResponse]
