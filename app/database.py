from datetime import datetime
from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Household(Base):
    __tablename__ = 'households'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    users = relationship('User', back_populates='household')
    meal_plans = relationship('MealPlan', back_populates='household')

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey('households.id'))
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    dietary_preferences = Column(ARRAY(String), default=[])
    disliked_foods = Column(ARRAY(String), default=[])
    household = relationship('Household', back_populates='users')

class Recipe(Base):
    __tablename__ = 'recipes'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    description = Column(Text)
    prep_time_minutes = Column(Integer)
    difficulty = Column(String)
    dietary_tags = Column(ARRAY(String), default=[])
    ingredients = Column(ARRAY(String), nullable=False)
    instructions = Column(Text, nullable=False)
    embedding = Column(Vector(1536))

class MealPlan(Base):
    __tablename__ = 'meal_plans'
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey('households.id'))
    week_start_date = Column(DateTime, nullable=False)
    is_locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    household = relationship('Household', back_populates='meal_plans')
    items = relationship('MealPlanItem', back_populates='meal_plan')

class MealPlanItem(Base):
    __tablename__ = 'meal_plan_items'
    id = Column(Integer, primary_key=True, index=True)
    meal_plan_id = Column(Integer, ForeignKey('meal_plans.id'))
    recipe_id = Column(Integer, ForeignKey('recipes.id'))
    day_of_week = Column(String, nullable=False)
    is_modified = Column(Boolean, default=False)
    meal_plan = relationship('MealPlan', back_populates='items')
    recipe = relationship('Recipe')
