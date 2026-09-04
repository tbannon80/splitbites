import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.session import AsyncSessionLocal
from app.models.pantry import PantryItem
from app.schemas.pantry import PantryItemCreate, PantryItemUpdate, PantryItemResponse
from app.routers.auth import get_current_user_and_household

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pantry", tags=["pantry"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/", response_model=List[PantryItemResponse])
async def get_pantry_items(
    current_auth=Depends(get_current_user_and_household),
    db: AsyncSession = Depends(get_db)
):
    """List all pantry staples for the authenticated household."""
    user, household = current_auth
    stmt = (
        select(PantryItem)
        .where(PantryItem.household_id == household.household_id)
        .order_by(PantryItem.item_name.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/", response_model=PantryItemResponse, status_code=status.HTTP_201_CREATED)
async def add_pantry_item(
    payload: PantryItemCreate,
    current_auth=Depends(get_current_user_and_household),
    db: AsyncSession = Depends(get_db)
):
    """Add a new staple item or update stock status if already present."""
    user, household = current_auth
    clean_name = payload.item_name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Item name cannot be empty.")

    stmt = select(PantryItem).where(
        PantryItem.household_id == household.household_id,
        func.lower(PantryItem.item_name) == clean_name.lower()
    )
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()
    if existing:
        existing.is_in_stock = payload.is_in_stock
        await db.commit()
        await db.refresh(existing)
        return existing

    new_item = PantryItem(
        household_id=household.household_id,
        item_name=clean_name,
        is_in_stock=payload.is_in_stock
    )
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)
    return new_item

@router.patch("/{pantry_id}", response_model=PantryItemResponse)
async def update_pantry_item(
    pantry_id: UUID,
    payload: PantryItemUpdate,
    current_auth=Depends(get_current_user_and_household),
    db: AsyncSession = Depends(get_db)
):
    """Update stock status or name of a pantry staple."""
    user, household = current_auth
    stmt = select(PantryItem).where(
        PantryItem.pantry_id == pantry_id,
        PantryItem.household_id == household.household_id
    )
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pantry item not found.")

    if payload.is_in_stock is not None:
        item.is_in_stock = payload.is_in_stock
    elif payload.item_name is None:
        # Default toggle behavior when no fields explicitly supplied
        item.is_in_stock = not item.is_in_stock

    if payload.item_name is not None:
        clean_name = payload.item_name.strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="Item name cannot be empty.")
        item.item_name = clean_name

    await db.commit()
    await db.refresh(item)
    return item

@router.delete("/{pantry_id}")
async def delete_pantry_item(
    pantry_id: UUID,
    current_auth=Depends(get_current_user_and_household),
    db: AsyncSession = Depends(get_db)
):
    """Remove an item from pantry staples."""
    user, household = current_auth
    stmt = select(PantryItem).where(
        PantryItem.pantry_id == pantry_id,
        PantryItem.household_id == household.household_id
    )
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pantry item not found.")

    await db.delete(item)
    await db.commit()
    return {"message": "Pantry item removed successfully", "pantry_id": str(pantry_id)}
