from sqlalchemy import Column, String, Boolean, Date, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.session import Base
import uuid

class MealPlan(Base):
    __tablename__ = "meal_plans"

    plan_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.household_id", ondelete="CASCADE"), nullable=True)
    week_start_date = Column(Date, nullable=False)
    is_locked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("MealPlanItem", back_populates="meal_plan", cascade="all, delete-orphan", lazy="selectin")

class MealPlanItem(Base):
    __tablename__ = "meal_plan_items"

    item_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meal_plan_id = Column(UUID(as_uuid=True), ForeignKey("meal_plans.plan_id", ondelete="CASCADE"), nullable=False)
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("recipes.recipe_id", ondelete="SET NULL"), nullable=True)
    day_of_week = Column(String(20), nullable=False)
    servings = Column(Integer, default=4, nullable=False, server_default="4")
    is_modified = Column(Boolean, default=False)
    fallback_applied = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meal_plan = relationship("MealPlan", back_populates="items")
    recipe = relationship("Recipe", lazy="selectin")
