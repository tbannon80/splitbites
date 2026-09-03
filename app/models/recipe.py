from sqlalchemy import Column, String, Integer, Text, Boolean, DECIMAL, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.database.session import Base
import uuid

class DietaryPreference(Base):
    __tablename__ = "dietary_preferences"
    preference_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    preference_name = Column(String(50), unique=True, nullable=False)

class Recipe(Base):
    __tablename__ = "recipes"
    recipe_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    prep_time_minutes = Column(Integer)
    difficulty_level = Column(String(50))
    instructions = Column(JSONB, nullable=False)
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    embedding = Column(Vector(1536), nullable=True)

class Ingredient(Base):
    __tablename__ = "ingredients"
    ingredient_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingredient_name = Column(String(255), unique=True, nullable=False)
    default_unit = Column(String(50))

class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("recipes.recipe_id", ondelete="CASCADE"), primary_key=True)
    ingredient_id = Column(UUID(as_uuid=True), ForeignKey("ingredients.ingredient_id", ondelete="CASCADE"), primary_key=True)
    quantity = Column(DECIMAL(10, 2), nullable=False)
    unit = Column(String(50), nullable=False)
