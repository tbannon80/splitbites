from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database.session import Base
import uuid

class Household(Base):
    __tablename__ = "households"

    household_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class HouseholdMember(Base):
    __tablename__ = "household_members"

    household_id = Column(UUID(as_uuid=True), ForeignKey("households.household_id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(50), default="member")

class HouseholdDietaryRestriction(Base):
    __tablename__ = "household_dietary_restrictions"

    household_id = Column(UUID(as_uuid=True), ForeignKey("households.household_id", ondelete="CASCADE"), primary_key=True)
    preference_id = Column(UUID(as_uuid=True), ForeignKey("dietary_preferences.preference_id", ondelete="CASCADE"), primary_key=True)
