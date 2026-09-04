import secrets
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.session import Base

class Household(Base):
    __tablename__ = "households"

    household_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_name = Column(String(100), nullable=False)
    busy_days = Column(JSONB, default=list, nullable=False, server_default='[]')
    busy_max_prep_minutes = Column(Integer, default=20, nullable=False, server_default='20')
    calendar_feed_token = Column(String(64), unique=True, default=lambda: secrets.token_urlsafe(32), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    dietary_preferences = relationship(
        "DietaryPreference",
        secondary="household_dietary_restrictions",
        lazy="selectin"
    )
    recipes = relationship(
        "Recipe",
        secondary="household_recipes",
        lazy="selectin"
    )

class HouseholdMember(Base):
    __tablename__ = "household_members"

    household_id = Column(UUID(as_uuid=True), ForeignKey("households.household_id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(50), default="member")

class HouseholdDietaryRestriction(Base):
    __tablename__ = "household_dietary_restrictions"

    household_id = Column(UUID(as_uuid=True), ForeignKey("households.household_id", ondelete="CASCADE"), primary_key=True)
    preference_id = Column(UUID(as_uuid=True), ForeignKey("dietary_preferences.preference_id", ondelete="CASCADE"), primary_key=True)

class HouseholdRecipe(Base):
    __tablename__ = "household_recipes"

    household_id = Column(UUID(as_uuid=True), ForeignKey("households.household_id", ondelete="CASCADE"), primary_key=True)
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("recipes.recipe_id", ondelete="CASCADE"), primary_key=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

