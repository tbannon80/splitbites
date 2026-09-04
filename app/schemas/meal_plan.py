from pydantic import BaseModel, ConfigDict, Field
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
    item_id: Optional[str] = None
    recipe_id: str
    title: str
    description: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    difficulty_level: Optional[str] = None
    servings: Optional[int] = 4
    default_servings: Optional[int] = 4
    is_modified: Optional[bool] = False
    fallback_applied: Optional[bool] = False
    nutrition_per_serving: Optional[Dict[str, Any]] = Field(default_factory=dict)
    daily_nutrition: Optional[Dict[str, Any]] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True, extra="ignore")

class WeeklyMealPlanResponse(BaseModel):
    status: str
    plan_id: Optional[str] = None
    plan_type: str
    week_start_date: Optional[str] = None
    is_locked: bool = False
    meals: Dict[str, MealSlotResponse]
    daily_nutrition: Optional[Dict[str, Any]] = Field(default_factory=dict)
    weekly_avg_daily_calories: Optional[float] = None
    weekly_avg_protein_g: Optional[float] = None
    weekly_avg_carbs_g: Optional[float] = None
    weekly_avg_fat_g: Optional[float] = None
    weekly_macro_averages: Optional[Dict[str, Any]] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True, extra="ignore")

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

class SlotAssignment(BaseModel):
    day_of_week: str
    recipe_id: UUID
    force: bool = False

class ServingsUpdateRequest(BaseModel):
    servings: int = Field(..., ge=1, le=20)

