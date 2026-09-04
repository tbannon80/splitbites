from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any, Union
from uuid import UUID
from datetime import datetime

class RecipeIngredientItem(BaseModel):
    name: str
    quantity: float = 1.0
    unit: str = "units"
    default_unit: Optional[str] = None

class RecipeInstructionItem(BaseModel):
    step: int
    text: str

class RecipeCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    prep_time_minutes: int = 30
    difficulty_level: str = "easy"
    default_servings: int = 4
    ingredients: List[RecipeIngredientItem] = []
    instructions: Union[List[RecipeInstructionItem], List[str], str] = []
    dietary_tags: Optional[List[str]] = []
    nutrition_per_serving: Optional[Dict[str, Any]] = Field(default_factory=dict)
    is_public: bool = True
    creator_id: Optional[UUID] = None

class RecipeResponse(BaseModel):
    recipe_id: UUID
    title: str
    description: Optional[str] = None
    prep_time_minutes: Optional[int] = None
    difficulty_level: Optional[str] = None
    default_servings: int = 4
    instructions: List[Dict[str, Any]]
    ingredients: List[Dict[str, Any]]
    nutrition_per_serving: Optional[Dict[str, Any]] = Field(default_factory=dict)
    dietary_tags: List[str] = []
    is_public: bool = True
    has_embedding: bool = True
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
