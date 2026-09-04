import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database.session import Base

DEFAULT_PANTRY_STAPLES = [
    "Salt",
    "Black Pepper",
    "Olive Oil",
    "Vegetable Oil",
    "Garlic Powder",
    "All-Purpose Flour",
    "Granulated Sugar",
]

class PantryItem(Base):
    __tablename__ = "pantry_items"

    pantry_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id = Column(UUID(as_uuid=True), ForeignKey("households.household_id", ondelete="CASCADE"), nullable=False)
    item_name = Column(String(100), nullable=False)
    is_in_stock = Column(Boolean, default=True, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("household_id", "item_name", name="uq_pantry_items_household_item"),
    )

async def seed_default_pantry_staples(household_id: uuid.UUID, db) -> None:
    from sqlalchemy import select
    for staple in DEFAULT_PANTRY_STAPLES:
        stmt = select(PantryItem).where(
            PantryItem.household_id == household_id,
            func.lower(PantryItem.item_name) == staple.lower()
        )
        res = await db.execute(stmt)
        if not res.scalar_one_or_none():
            db.add(PantryItem(household_id=household_id, item_name=staple, is_in_stock=True))
    await db.flush()

