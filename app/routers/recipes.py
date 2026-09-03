from decimal import Decimal
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.database.session import AsyncSessionLocal
from app.models import (
    Recipe,
    Ingredient,
    RecipeIngredient,
    DietaryPreference,
    RecipeDietaryTag,
    RetailerPricing,
    HouseholdRecipe,
    Household,
    User,
)
from app.schemas.recipe import RecipeCreateRequest, RecipeResponse
from app.services.embedding import get_embedding
from app.services.auth import decode_access_token

router = APIRouter(prefix="/api/recipes", tags=["recipes"])
security = HTTPBearer(auto_error=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def get_auth_token_payload(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[Dict[str, Any]]:
    if not credentials:
        return None
    return decode_access_token(credentials.credentials)

def require_auth_token_payload(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication credentials required")
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    return payload

def format_recipe_response(recipe: Recipe) -> Dict[str, Any]:
    tags = [p.preference_name for p in recipe.dietary_preferences] if recipe.dietary_preferences else []
    return {
        "recipe_id": str(recipe.recipe_id),
        "title": recipe.title,
        "description": recipe.description,
        "prep_time_minutes": recipe.prep_time_minutes,
        "difficulty_level": recipe.difficulty_level,
        "instructions": recipe.instructions or [],
        "ingredients": recipe.ingredients or [],
        "dietary_tags": tags,
        "is_public": recipe.is_public,
        "has_embedding": recipe.embedding is not None,
        "created_at": recipe.created_at
    }

def normalize_instructions(raw_inst: Union[List[Any], str]) -> List[Dict[str, Any]]:
    if isinstance(raw_inst, str):
        lines = [l.strip() for l in raw_inst.split("\n") if l.strip()]
        return [{"step": i + 1, "text": l.lstrip("0123456789.- ")} for i, l in enumerate(lines)]
    elif isinstance(raw_inst, list):
        steps = []
        for i, item in enumerate(raw_inst):
            if isinstance(item, str):
                steps.append({"step": i + 1, "text": item.strip()})
            elif isinstance(item, dict):
                steps.append({"step": item.get("step", i + 1), "text": item.get("text", "")})
            elif hasattr(item, "text"):
                steps.append({"step": getattr(item, "step", i + 1), "text": getattr(item, "text")})
        return steps
    return []

@router.post("/", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    payload: RecipeCreateRequest,
    auth_data: Optional[Dict[str, Any]] = Depends(get_auth_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """
    Accepts user-submitted recipe ingredients, instructions, and dietary tags.
    Automatically computes a 1536-dimensional pgvector embedding using embedding.py,
    registers the recipe in the household pool, and provisions
    baseline retailer pricing for immediate grocery aggregation compatibility.
    """
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Recipe title is required.")

    # 1. Normalize instructions
    formatted_instructions = normalize_instructions(payload.instructions)
    if not formatted_instructions:
        formatted_instructions = [{"step": 1, "text": "Prepare and serve according to preference."}]

    # 2. Normalize ingredients
    formatted_ingredients = []
    for item in payload.ingredients:
        ing_name = item.name.strip()
        if ing_name:
            formatted_ingredients.append({
                "name": ing_name,
                "quantity": float(item.quantity),
                "unit": item.unit.strip() or "ea",
                "default_unit": (item.default_unit or item.unit or "ea").strip()
            })

    # 3. Generate 1536-dim pgvector embedding
    tag_str = ", ".join(payload.dietary_tags or [])
    ing_names_str = ", ".join(i["name"] for i in formatted_ingredients)
    embed_text = f"{payload.title}. {payload.description or ''}. Tags: {tag_str}. Ingredients: {ing_names_str}."
    embedding_vector = await get_embedding(embed_text)

    # 4. Determine creator and household
    creator_id = UUID(auth_data["sub"]) if auth_data and "sub" in auth_data else payload.creator_id
    household_id = UUID(auth_data["hid"]) if auth_data and "hid" in auth_data else None

    # 5. Insert Recipe
    new_recipe = Recipe(
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        prep_time_minutes=payload.prep_time_minutes,
        difficulty_level=payload.difficulty_level.lower(),
        instructions=formatted_instructions,
        ingredients=formatted_ingredients,
        is_public=payload.is_public,
        creator_id=creator_id,
        household_id=household_id,
        embedding=embedding_vector
    )
    db.add(new_recipe)
    await db.flush()

    # Link to household's personal recipe book
    if household_id:
        await db.execute(
            text("INSERT INTO household_recipes (household_id, recipe_id) VALUES (:hid, :rid) ON CONFLICT DO NOTHING"),
            {"hid": household_id, "rid": new_recipe.recipe_id}
        )

    # 5. Handle Dietary Tags
    if payload.dietary_tags:
        for tag in payload.dietary_tags:
            clean_tag = tag.strip().lower()
            if not clean_tag:
                continue
            pref_stmt = select(DietaryPreference).where(DietaryPreference.preference_name == clean_tag)
            pref_res = await db.execute(pref_stmt)
            pref = pref_res.scalar_one_or_none()
            if not pref:
                pref = DietaryPreference(preference_name=clean_tag)
                db.add(pref)
                await db.flush()

            # Insert link
            await db.execute(
                text(
                    "INSERT INTO recipe_dietary_tags (recipe_id, preference_id) "
                    "VALUES (:rid, :pid) ON CONFLICT DO NOTHING"
                ),
                {"rid": new_recipe.recipe_id, "pid": pref.preference_id}
            )

    # 6. Handle Ingredients & Multi-Store Pricing
    retailer_multipliers = {
        "Aldi": 0.88,
        "Walmart": 0.95,
        "Meijer": 1.04,
        "Amazon": 1.18,
    }

    for ing_data in formatted_ingredients:
        ing_name = ing_data["name"]
        unit = ing_data["unit"]
        qty = ing_data["quantity"]

        # Fetch or create Ingredient record
        ing_stmt = select(Ingredient).where(Ingredient.ingredient_name == ing_name)
        ing_res = await db.execute(ing_stmt)
        db_ing = ing_res.scalar_one_or_none()

        if not db_ing:
            db_ing = Ingredient(ingredient_name=ing_name, default_unit=unit)
            db.add(db_ing)
            await db.flush()

        # Link recipe_ingredients
        await db.execute(
            text(
                "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit) "
                "VALUES (:rid, :iid, :qty, :unit) "
                "ON CONFLICT (recipe_id, ingredient_id) DO UPDATE SET quantity = :qty, unit = :unit"
            ),
            {"rid": new_recipe.recipe_id, "iid": db_ing.ingredient_id, "qty": qty, "unit": unit}
        )

        # Ensure retailer pricing exists for all target stores
        for retailer, mult in retailer_multipliers.items():
            price_stmt = select(RetailerPricing).where(
                RetailerPricing.ingredient_id == db_ing.ingredient_id,
                RetailerPricing.retailer_name == retailer
            )
            price_res = await db.execute(price_stmt)
            existing_price = price_res.scalar_one_or_none()

            if not existing_price:
                # Estimate a reasonable baseline unit price
                base = 2.99
                name_l = ing_name.lower()
                if any(k in name_l for k in ("salmon", "beef", "shrimp", "steak")):
                    base = 7.99
                elif any(k in name_l for k in ("chicken", "pork", "turkey")):
                    base = 4.99
                elif any(k in name_l for k in ("cheese", "butter", "oil")):
                    base = 3.99
                elif any(k in name_l for k in ("produce", "garlic", "lemon", "herb")):
                    base = 1.49

                store_price = round(base * mult, 2)
                db.add(
                    RetailerPricing(
                        ingredient_id=db_ing.ingredient_id,
                        retailer_name=retailer,
                        price=Decimal(str(store_price)),
                        package_size=f"1 {unit}"
                    )
                )

    await db.commit()

    # Re-query with eager load
    stmt = (
        select(Recipe)
        .options(selectinload(Recipe.dietary_preferences))
        .where(Recipe.recipe_id == new_recipe.recipe_id)
    )
    res = await db.execute(stmt)
    full_recipe = res.scalar_one()

    return format_recipe_response(full_recipe)

@router.get("/", response_model=List[RecipeResponse])
async def list_recipes(
    tag: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """List available recipes with optional dietary tag filtering."""
    stmt = select(Recipe).options(selectinload(Recipe.dietary_preferences)).order_by(Recipe.created_at.desc()).limit(limit)
    res = await db.execute(stmt)
    recipes = res.scalars().all()

    if tag:
        clean_tag = tag.strip().lower()
        recipes = [
            r for r in recipes
            if clean_tag in [p.preference_name.lower() for p in r.dietary_preferences]
        ]

    return [format_recipe_response(r) for r in recipes]

@router.get("/my-recipes")
async def list_my_recipes(
    auth_data: Dict[str, Any] = Depends(require_auth_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns all recipes currently in the authenticated user's family recipe book.
    """
    hid = UUID(auth_data["hid"])
    stmt = (
        select(Recipe, HouseholdRecipe.added_at)
        .join(HouseholdRecipe, Recipe.recipe_id == HouseholdRecipe.recipe_id)
        .where(HouseholdRecipe.household_id == hid)
        .options(selectinload(Recipe.dietary_preferences))
        .order_by(HouseholdRecipe.added_at.desc(), Recipe.title.asc())
    )
    res = await db.execute(stmt)
    rows = res.all()

    items = []
    for r, added_at in rows:
        tags = [p.preference_name for p in r.dietary_preferences] if r.dietary_preferences else []
        items.append({
            "recipe_id": str(r.recipe_id),
            "title": r.title,
            "description": r.description,
            "prep_time_minutes": r.prep_time_minutes,
            "difficulty_level": r.difficulty_level,
            "instructions": r.instructions or [],
            "ingredients": r.ingredients or [],
            "dietary_tags": tags,
            "is_public": r.is_public,
            "is_created_by_family": r.household_id == hid,
            "added_at": added_at.isoformat() if added_at else None
        })
    return items

@router.delete("/my-recipes/{recipe_id}")
async def remove_from_my_recipes(
    recipe_id: UUID,
    auth_data: Dict[str, Any] = Depends(require_auth_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """
    Removes a recipe from the family group's recipe book so it no longer auto-populates
    their meal plans or shows in their recipe list.
    """
    hid = UUID(auth_data["hid"])
    del_stmt = text("DELETE FROM household_recipes WHERE household_id = :hid AND recipe_id = :rid")
    res = await db.execute(del_stmt, {"hid": hid, "rid": recipe_id})
    await db.commit()

    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Recipe not found in your family recipe book.")

    return {"status": "success", "message": "Recipe removed from your family recipe book."}

@router.get("/community")
async def list_community_recipes(
    auth_data: Optional[Dict[str, Any]] = Depends(get_auth_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns public recipes submitted by other family groups that are NOT currently
    in the active family group's recipe book.
    """
    hid = UUID(auth_data["hid"]) if auth_data and "hid" in auth_data else None

    if hid:
        subquery = select(HouseholdRecipe.recipe_id).where(HouseholdRecipe.household_id == hid)
        stmt = (
            select(Recipe, Household.household_name, User.full_name)
            .outerjoin(Household, Recipe.household_id == Household.household_id)
            .outerjoin(User, Recipe.creator_id == User.user_id)
            .where(
                Recipe.is_public == True,
                ~Recipe.recipe_id.in_(subquery)
            )
            .options(selectinload(Recipe.dietary_preferences))
            .order_by(Recipe.created_at.desc())
        )
    else:
        stmt = (
            select(Recipe, Household.household_name, User.full_name)
            .outerjoin(Household, Recipe.household_id == Household.household_id)
            .outerjoin(User, Recipe.creator_id == User.user_id)
            .where(Recipe.is_public == True)
            .options(selectinload(Recipe.dietary_preferences))
            .order_by(Recipe.created_at.desc())
        )

    res = await db.execute(stmt)
    rows = res.all()

    items = []
    for r, h_name, u_name in rows:
        tags = [p.preference_name for p in r.dietary_preferences] if r.dietary_preferences else []
        submitted_by = h_name if h_name else (u_name if u_name else "SplitBites Community")
        items.append({
            "recipe_id": str(r.recipe_id),
            "title": r.title,
            "description": r.description,
            "prep_time_minutes": r.prep_time_minutes,
            "difficulty_level": r.difficulty_level,
            "instructions": r.instructions or [],
            "ingredients": r.ingredients or [],
            "dietary_tags": tags,
            "submitted_by_family": submitted_by,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })
    return items

@router.post("/community/{recipe_id}/add")
async def add_community_recipe_to_book(
    recipe_id: UUID,
    auth_data: Dict[str, Any] = Depends(require_auth_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """
    Adds a recipe submitted by another family group (or community) to the authenticated family's recipe book.
    """
    hid = UUID(auth_data["hid"])

    # Verify recipe exists
    chk_stmt = select(Recipe).where(Recipe.recipe_id == recipe_id)
    chk_res = await db.execute(chk_stmt)
    rec = chk_res.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    ins_stmt = text(
        "INSERT INTO household_recipes (household_id, recipe_id) VALUES (:hid, :rid) ON CONFLICT DO NOTHING"
    )
    await db.execute(ins_stmt, {"hid": hid, "rid": recipe_id})
    await db.commit()

    return {
        "status": "success",
        "message": f"'{rec.title}' added to your family recipe book!",
        "recipe_id": str(rec.recipe_id)
    }

@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(recipe_id: UUID, db: AsyncSession = Depends(get_db)):
    """Fetch recipe details by ID."""
    stmt = (
        select(Recipe)
        .options(selectinload(Recipe.dietary_preferences))
        .where(Recipe.recipe_id == recipe_id)
    )
    res = await db.execute(stmt)
    recipe = res.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail=f"Recipe {recipe_id} not found.")

    return format_recipe_response(recipe)

from pydantic import BaseModel, HttpUrl
from app.services.recipe_scraper import extract_recipe_from_url

class ExtractRecipeUrlRequest(BaseModel):
    url: str

@router.post("/extract-url")
async def extract_recipe_url(payload: ExtractRecipeUrlRequest):
    """
    Extracts structured recipe title, description, prep time, difficulty,
    ingredients, instructions, and dietary tags from any online recipe URL.
    """
    clean_url = payload.url.strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")
    try:
        data = await extract_recipe_from_url(clean_url)
        return data
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to scrape recipe from URL: {str(e)}")
