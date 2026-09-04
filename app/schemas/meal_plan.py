from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import date

DEFAULT_7_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

class MealPlanGenerateRequest(BaseModel):
    household_id: Optional[UUID] = None
    target_date: Optional[date] = None
    dietary_tags: Optional[List[str]] = None
    busy_days: Optional[List[str]] = None
    busy_max_prep_minutes: Optional[int] = None
    target_days: Optional[List[str]] = None
    days_count: Optional[int] = None
    persist: bool = True

class MealSlotResponse(BaseModel):
    recipe_id: str
    title: str
    description: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    difficulty_level: Optional[str] = None
    is_modified: Optional[bool] = False
    fallback_applied: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)

class WeeklyMealPlanResponse(BaseModel):
    status: str
    plan_id: Optional[str] = None
    plan_type: str
    week_start_date: Optional[str] = None
    is_locked: bool = False
    meals: Dict[str, MealSlotResponse]

class MealPlanSwapRequest(BaseModel):
    day_of_week: str
    new_recipe_id: Optional[UUID] = None
    use_vector_similarity: bool = True

class MealPlanLockRequest(BaseModel):
    lock: bool = True

class MealPlanShuffleRequest(BaseModel):
    preserve_modified: bool = True

class MealPlanAddDayRequest(BaseModel):
    day_of_week: str
    recipe_id: Optional[UUID] = None

class MealPlanSubtractDayRequest(BaseModel):
    day_of_week: str

class MealPlanDaysUpdateRequest(BaseModel):
    target_days: List[str]
