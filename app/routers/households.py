from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import List
import secrets

from app.database.session import AsyncSessionLocal
from app.models import Household, HouseholdDietaryRestriction, DietaryPreference
from app.schemas.household import (
    HouseholdCreate,
    HouseholdResponse,
    HouseholdDietaryUpdateRequest,
    HouseholdScheduleUpdateRequest,
    HouseholdUpdate,
)

router = APIRouter(prefix="/api/households", tags=["households"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def format_household(h: Household) -> HouseholdResponse:
    prefs = [p.preference_name for p in h.dietary_preferences] if h.dietary_preferences else []
    return HouseholdResponse(
        household_id=h.household_id,
        household_name=h.household_name,
        calendar_feed_token=h.calendar_feed_token,
        dietary_preferences=prefs,
        busy_days=h.busy_days if h.busy_days is not None else ["Tuesday", "Thursday"],
        busy_max_prep_minutes=h.busy_max_prep_minutes if h.busy_max_prep_minutes is not None else 20,
        created_at=h.created_at
    )

@router.post("/", response_model=HouseholdResponse)
async def create_household(payload: HouseholdCreate, db: AsyncSession = Depends(get_db)):
    """Create a household and associate dietary restrictions."""
    new_h = Household(
        household_name=payload.household_name,
        calendar_feed_token=secrets.token_urlsafe(32),
        busy_days=payload.busy_days if payload.busy_days is not None else ["Tuesday", "Thursday"],
        busy_max_prep_minutes=payload.busy_max_prep_minutes if payload.busy_max_prep_minutes is not None else 20
    )
    db.add(new_h)
    await db.flush()

    if payload.dietary_preferences:
        for pref_name in payload.dietary_preferences:
            clean_name = pref_name.strip().lower()
            stmt = select(DietaryPreference).where(DietaryPreference.preference_name == clean_name)
            res = await db.execute(stmt)
            pref = res.scalar_one_or_none()
            if not pref:
                pref = DietaryPreference(preference_name=clean_name)
                db.add(pref)
                await db.flush()

            link = HouseholdDietaryRestriction(household_id=new_h.household_id, preference_id=pref.preference_id)
            db.add(link)

    await db.commit()

    stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == new_h.household_id)
    res = await db.execute(stmt)
    full_h = res.scalar_one()
    return format_household(full_h)

@router.get("/{household_id}", response_model=HouseholdResponse)
async def get_household(household_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get household by ID."""
    stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == household_id)
    res = await db.execute(stmt)
    h = res.scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Household not found")
    return format_household(h)

@router.get("/", response_model=List[HouseholdResponse])
async def list_households(db: AsyncSession = Depends(get_db)):
    """List all households."""
    stmt = select(Household).options(selectinload(Household.dietary_preferences)).order_by(Household.created_at.desc())
    res = await db.execute(stmt)
    households = res.scalars().all()
    return [format_household(h) for h in households]

@router.put("/{household_id}/dietary-preferences", response_model=HouseholdResponse)
async def update_dietary_preferences(household_id: UUID, payload: HouseholdDietaryUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update dietary preferences for a household."""
    stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == household_id)
    res = await db.execute(stmt)
    h = res.scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Household not found")

    await db.execute(delete(HouseholdDietaryRestriction).where(HouseholdDietaryRestriction.household_id == household_id))

    for pref_name in payload.dietary_preferences:
        clean_name = pref_name.strip().lower()
        pref_stmt = select(DietaryPreference).where(DietaryPreference.preference_name == clean_name)
        pref_res = await db.execute(pref_stmt)
        pref = pref_res.scalar_one_or_none()
        if not pref:
            pref = DietaryPreference(preference_name=clean_name)
            db.add(pref)
            await db.flush()
        db.add(HouseholdDietaryRestriction(household_id=household_id, preference_id=pref.preference_id))

    await db.commit()

    res = await db.execute(stmt)
    full_h = res.scalar_one()
    return format_household(full_h)

@router.put("/{household_id}/schedule", response_model=HouseholdResponse)
async def update_household_schedule(
    household_id: UUID,
    payload: HouseholdScheduleUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update busy weeknight schedule preferences for a household."""
    stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == household_id)
    res = await db.execute(stmt)
    h = res.scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Household not found")

    h.busy_days = payload.busy_days
    h.busy_max_prep_minutes = payload.busy_max_prep_minutes
    await db.commit()

    res = await db.execute(stmt)
    full_h = res.scalar_one()
    return format_household(full_h)

@router.post("/{household_id}/regenerate-calendar-token", response_model=HouseholdResponse)
async def regenerate_calendar_token(household_id: UUID, db: AsyncSession = Depends(get_db)):
    """Regenerates the calendar subscription feed token for a household, invalidating previous feed links."""
    stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == household_id)
    res = await db.execute(stmt)
    h = res.scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Household not found")

    h.calendar_feed_token = secrets.token_urlsafe(32)
    await db.commit()
    await db.refresh(h)
    return format_household(h)
