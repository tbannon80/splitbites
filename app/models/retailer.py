from sqlalchemy import Column, String, DECIMAL, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.session import Base
import uuid

class RetailerPricing(Base):
    __tablename__ = "retailer_pricing"

    pricing_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingredient_id = Column(UUID(as_uuid=True), ForeignKey("ingredients.ingredient_id", ondelete="CASCADE"), nullable=False)
    retailer_name = Column(String(100), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    package_size = Column(String(100), nullable=True)
    last_updated = Column(DateTime(timezone=True), server_default=func.now())

    ingredient = relationship("Ingredient", lazy="selectin")
