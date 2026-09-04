import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4
import httpx
from bs4 import BeautifulSoup

from app.services.recipe_scraper import (
    parse_ingredient_line,
    parse_quantity,
    strip_non_ingredient_parentheticals,
    parse_recipe_from_html_heuristics,
    extract_recipe_from_url,
    UNIT_NORMALIZATION,
)
from app.main import app

# Fixture HTML with standard Schema.org JSON-LD
SCHEMA_ORG_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Pan-Seared Salmon with Rosemary - Kitchen Delights</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "Pan-Seared Rosemary Salmon",
        "description": "Crispy seared salmon fillets with fresh rosemary and garlic.",
        "prepTime": "PT10M",
        "cookTime": "PT10M",
        "totalTime": "PT20M",
        "recipeIngredient": [
            "1-2 lbs fresh salmon fillets",
            "1 ½ tablespoons olive oil (divided)",
            "2-3 cloves garlic (minced)",
            "1 pinch sea salt",
            "1 bunch fresh dill"
        ],
        "recipeInstructions": [
            {"@type": "HowToStep", "text": "Pat salmon fillets dry with paper towels."},
            {"@type": "HowToStep", "text": "Heat 1 tablespoon olive oil in a heavy skillet over medium-high heat."},
            {"@type": "HowToStep", "text": "Sear salmon skin-side down with minced garlic and herbs for 4-5 minutes."}
        ]
    }
    </script>
</head>
<body>
    <h1>Pan-Seared Rosemary Salmon</h1>
</body>
</html>
"""

# Fixture HTML without Schema.org JSON-LD, using WPRM (WP Recipe Maker) classes
WPRM_FALLBACK_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Hearty Slow Cooker Beef Stew - Rustic Foodie</title>
</head>
<body>
    <div class="site-content">
        <div class="wprm-recipe-container wprm-recipe-template-classic">
            <h2 class="wprm-recipe-name">Hearty Slow Cooker Beef Stew</h2>
            <div class="wprm-recipe-summary">A cozy, comforting beef stew packed with tender vegetables and rich broth.</div>
            <div class="wprm-recipe-times-container">
                <span class="wprm-recipe-total-time">45 mins</span>
            </div>
            <div class="wprm-recipe-ingredients-container">
                <ul class="wprm-recipe-ingredients">
                    <li class="wprm-recipe-ingredient">1 - 2 lbs beef chuck roast, diced</li>
                    <li class="wprm-recipe-ingredient">3 cups beef broth</li>
                    <li class="wprm-recipe-ingredient">1 (15 oz) can diced tomatoes</li>
                    <li class="wprm-recipe-ingredient">2-3 cloves garlic (minced)</li>
                    <li class="wprm-recipe-ingredient">2 tablespoons olive oil (divided)</li>
                    <li class="wprm-recipe-ingredient">1 pinch black pepper</li>
                </ul>
            </div>
            <div class="wprm-recipe-instructions-container">
                <ol class="wprm-recipe-instructions">
                    <li class="wprm-recipe-instruction">Sear the beef cubes in olive oil until browned.</li>
                    <li class="wprm-recipe-instruction">Place all ingredients in the slow cooker.</li>
                    <li class="wprm-recipe-instruction">Cook on low for 8 hours until beef is tender.</li>
                </ol>
            </div>
        </div>
    </div>
</body>
</html>
"""

# Fixture HTML for Tasty Recipes blog layout
TASTY_RECIPES_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Tuscan Garlic Chicken</title>
</head>
<body>
    <div class="tasty-recipes">
        <h2 class="tasty-recipes-title">Creamy Tuscan Garlic Chicken</h2>
        <div class="tasty-recipes-description">Juicy pan-seared chicken cutlets in a creamy sun-dried tomato sauce.</div>
        <span class="tasty-recipes-prep-time">20 minutes</span>
        <ul class="tasty-recipes-ingredients">
            <li>1 ½ lbs chicken breast (about 3 cutlets), diced</li>
            <li>¾ cup heavy cream</li>
            <li>2 tablespoons butter</li>
            <li>2-3 cloves garlic, minced</li>
            <li>1 bunch fresh basil</li>
        </ul>
        <ul class="tasty-recipes-instructions">
            <li>Sear seasoned chicken cutlets until golden brown.</li>
            <li>Add garlic, cream, and butter; simmer until thickened.</li>
        </ul>
    </div>
</body>
</html>
"""

# Fixture HTML for a non-recipe page (no JSON-LD and no recipe markup)
NON_RECIPE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>My Personal Travel Diary</title>
</head>
<body>
    <h1>Trip to the Mountains</h1>
    <p>We hiked through the pine forest and camped under the stars. The weather was brisk and crisp.</p>
</body>
</html>
"""

def test_edge_case_fraction_and_range_parsing():
    """
    Test c: Edge-case fraction and range parsing.
    - Composite unicode fractions ('1 ½', '¾', '2 ¾', '1½')
    - Multi-token ranges ('1-2 lbs', '1 - 2 lbs', '1 to 2 lbs', '2-3 cloves') -> parsed as ceiling
    - Stripping non-ingredient parenthetical text ('(about 4 breasts)', '(divided)', '(15 oz)')
    - Mapping measurement units to standard retailer pricing packaging units
    """
    # 1. Composite unicode fractions
    f1 = parse_ingredient_line("1 ½ cups all-purpose flour")
    assert f1["quantity"] == 1.5
    assert f1["unit"] == "cups"
    assert "Flour" in f1["name"]

    f2 = parse_ingredient_line("¾ tsp kosher salt")
    assert f2["quantity"] == 0.75
    assert f2["unit"] == "tsp"
    assert f2["name"] == "Kosher Salt"

    f3 = parse_ingredient_line("2 ¾ cups chicken broth")
    assert f3["quantity"] == 2.75
    assert f3["unit"] == "cups"
    assert f3["name"] == "Chicken Broth"

    f4 = parse_ingredient_line("1½ cups milk")
    assert f4["quantity"] == 1.5
    assert f4["unit"] == "cups"

    # 2. Multi-token ranges parsed as ceiling
    r1 = parse_ingredient_line("1-2 lbs boneless skinless chicken breasts (about 4 breasts), diced")
    assert r1["quantity"] == 2.0, "Multi-token range 1-2 lbs must resolve to 2.0 lbs ceiling"
    assert r1["unit"] == "lbs"
    assert "about 4 breasts" not in r1["name"]
    assert "diced" not in r1["name"].lower()
    assert r1["name"] == "Boneless Skinless Chicken Breasts"

    r2 = parse_ingredient_line("1 - 2 lbs ground beef")
    assert r2["quantity"] == 2.0, "Spaced range 1 - 2 lbs must resolve to 2.0 lbs ceiling"
    assert r2["unit"] == "lbs"
    assert r2["name"] == "Ground Beef"

    r3 = parse_ingredient_line("1 to 2 lbs pork chops")
    assert r3["quantity"] == 2.0, "'to' range 1 to 2 lbs must resolve to 2.0 lbs ceiling"
    assert r3["unit"] == "lbs"
    assert r3["name"] == "Pork Chops"

    r4 = parse_ingredient_line("2-3 cloves garlic (minced)")
    assert r4["quantity"] == 3.0, "Range 2-3 cloves must resolve to 3.0 cloves ceiling"
    assert r4["unit"] == "count"
    assert "minced" not in r4["name"].lower()
    assert r4["name"] == "Garlic"

    r5 = parse_ingredient_line("1/2 - 3/4 cup warm water")
    assert r5["quantity"] == 0.75, "Fractional range 1/2 - 3/4 must resolve to 0.75 ceiling"
    assert r5["unit"] == "cups"

    # 3. Stripping non-ingredient parenthetical text
    p1 = parse_ingredient_line("2 tablespoons olive oil (divided)")
    assert p1["quantity"] == 2.0
    assert p1["unit"] == "tbsp"
    assert "divided" not in p1["name"].lower()
    assert p1["name"] == "Olive Oil"

    p2 = parse_ingredient_line("1 (15 oz) can black beans, drained and rinsed")
    assert p2["quantity"] == 1.0
    assert p2["unit"] == "can"
    assert "15 oz" not in p2["name"]
    assert "drained" not in p2["name"].lower()
    assert p2["name"] == "Black Beans"

    # 4. Measurement unit normalization dictionary verification
    assert UNIT_NORMALIZATION["tbsp"] == "tbsp"
    assert UNIT_NORMALIZATION["tablespoon"] == "tbsp"
    assert UNIT_NORMALIZATION["tablespoons"] == "tbsp"
    assert UNIT_NORMALIZATION["tsp"] == "tsp"
    assert UNIT_NORMALIZATION["teaspoon"] == "tsp"
    assert UNIT_NORMALIZATION["cup"] == "cups"
    assert UNIT_NORMALIZATION["cups"] == "cups"
    assert UNIT_NORMALIZATION["oz"] == "oz"
    assert UNIT_NORMALIZATION["ounce"] == "oz"
    assert UNIT_NORMALIZATION["lb"] == "lbs"
    assert UNIT_NORMALIZATION["lbs"] == "lbs"
    assert UNIT_NORMALIZATION["pinch"] == "tsp"
    assert UNIT_NORMALIZATION["can"] == "can"
    assert UNIT_NORMALIZATION["clove"] == "count"
    assert UNIT_NORMALIZATION["bunch"] == "bunch"

@pytest.mark.asyncio
async def test_clean_schema_org_url_import():
    """
    Test a: Clean Schema.org URL import.
    Verifies that a URL containing Schema.org JSON-LD microdata correctly extracts
    title, prep time, difficulty, structured ingredients, instructions, and dietary tags.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = SCHEMA_ORG_HTML
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        data = await extract_recipe_from_url("https://kitchendelights.test/pan-seared-salmon")

    assert data["title"] == "Pan-Seared Rosemary Salmon"
    assert data["prep_time_minutes"] == 20
    assert data["difficulty_level"] == "quick"
    assert len(data["ingredients"]) == 5

    # Check that 1-2 lbs was parsed to ceiling 2.0 lbs
    salmon_ing = next((i for i in data["ingredients"] if "Salmon" in i["name"]), None)
    assert salmon_ing is not None
    assert salmon_ing["quantity"] == 2.0
    assert salmon_ing["unit"] == "lbs"

    # Check 1 ½ tablespoons olive oil
    oil_ing = next((i for i in data["ingredients"] if "Olive Oil" in i["name"]), None)
    assert oil_ing is not None
    assert oil_ing["quantity"] == 1.5
    assert oil_ing["unit"] == "tbsp"

    assert len(data["instructions"]) == 3
    assert "pescatarian" in data["dietary_tags"]

@pytest.mark.asyncio
async def test_non_standard_html_fallback_blog_import():
    """
    Test b: Non-standard HTML fallback blog import.
    Verifies Tier-2 HTML heuristic fallback parsing with BeautifulSoup
    when Schema.org JSON-LD is missing or incomplete (WPRM & Tasty Recipes).
    """
    # 1. WPRM (WP Recipe Maker) fallback
    wprm_resp = MagicMock()
    wprm_resp.status_code = 200
    wprm_resp.text = WPRM_FALLBACK_HTML
    wprm_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=wprm_resp):
        wprm_data = await extract_recipe_from_url("https://rusticfoodie.test/slow-cooker-beef-stew")

    assert wprm_data["title"] == "Hearty Slow Cooker Beef Stew"
    assert wprm_data["prep_time_minutes"] == 45
    assert len(wprm_data["ingredients"]) == 6

    # Verify range 1 - 2 lbs chuck roast parsed as ceiling 2.0 lbs
    beef_ing = next((i for i in wprm_data["ingredients"] if "Beef" in i["name"]), None)
    assert beef_ing is not None
    assert beef_ing["quantity"] == 2.0
    assert beef_ing["unit"] == "lbs"

    # Verify 1 (15 oz) can diced tomatoes parsed as 1.0 can
    tom_ing = next((i for i in wprm_data["ingredients"] if "Diced Tomatoes" in i["name"]), None)
    assert tom_ing is not None
    assert tom_ing["quantity"] == 1.0
    assert tom_ing["unit"] == "can"

    assert len(wprm_data["instructions"]) == 3

    # 2. Tasty Recipes fallback
    tasty_resp = MagicMock()
    tasty_resp.status_code = 200
    tasty_resp.text = TASTY_RECIPES_HTML
    tasty_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=tasty_resp):
        tasty_data = await extract_recipe_from_url("https://pinchofdelight.test/creamy-tuscan-chicken")

    assert tasty_data["title"] == "Creamy Tuscan Garlic Chicken"
    assert tasty_data["prep_time_minutes"] == 20
    assert len(tasty_data["ingredients"]) == 5

    chk_ing = next((i for i in tasty_data["ingredients"] if "Chicken" in i["name"]), None)
    assert chk_ing is not None
    assert chk_ing["quantity"] == 1.5
    assert chk_ing["unit"] == "lbs"
    assert "about 3 cutlets" not in chk_ing["name"]

@pytest.mark.asyncio
async def test_handling_invalid_urls_gracefully_http_422():
    """
    Test d: Handling invalid URLs gracefully with HTTP 422 Unprocessable Entity.
    Verifies that invalid URL protocols or URLs without recipe data return HTTP 422
    with a clean, descriptive JSON payload instead of an unhandled 500 error.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid URL scheme (ftp:// or non-http string)
        bad_scheme_resp = await client.post("/api/recipes/extract-url", json={"url": "ftp://files.example.com/recipe.pdf"})
        assert bad_scheme_resp.status_code == 422
        bad_scheme_json = bad_scheme_resp.json()
        assert "detail" in bad_scheme_json
        assert "Invalid URL" in bad_scheme_json["detail"]

        non_url_resp = await client.post("/api/recipes/extract-url", json={"url": "just_a_random_string"})
        assert non_url_resp.status_code == 422

        # 2. URL pointing to a non-recipe webpage (missing both JSON-LD and heuristic recipe markup)
        non_recipe_mock = MagicMock()
        non_recipe_mock.status_code = 200
        non_recipe_mock.text = NON_RECIPE_HTML
        non_recipe_mock.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", return_value=non_recipe_mock):
            extract_resp = await client.post("/api/recipes/extract-url", json={"url": "https://travel-blog.test/diary-entry"})
            assert extract_resp.status_code == 422
            extract_json = extract_resp.json()
            assert "detail" in extract_json
            assert "Failed to scrape recipe from URL" in extract_json["detail"]

        # 3. Import-url endpoint also rejects non-recipe URL with 422
        with patch("httpx.AsyncClient.get", return_value=non_recipe_mock):
            import_resp = await client.post("/api/recipes/import-url", json={"url": "https://travel-blog.test/diary-entry"})
            assert import_resp.status_code == 422
            import_json = import_resp.json()
            assert "detail" in import_json
            assert "Failed to scrape recipe from URL" in import_json["detail"]

@pytest.mark.asyncio
async def test_multi_tenancy_isolation_scraped_recipe():
    """
    Verifies multi-tenancy isolation:
    Scraped/imported recipes automatically link to the specified household's recipe book.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create Household A and Household B
        h_resp_a = await client.post("/api/households/", json={"household_name": "Family Scraper Alpha"})
        assert h_resp_a.status_code == 200
        hid_a = h_resp_a.json()["household_id"]

        h_resp_b = await client.post("/api/households/", json={"household_name": "Family Scraper Beta"})
        assert h_resp_b.status_code == 200
        hid_b = h_resp_b.json()["household_id"]

        # 2. Import recipe into Household A's recipe book
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SCHEMA_ORG_HTML
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            import_resp = await client.post(
                "/api/recipes/import-url",
                json={"url": "https://kitchendelights.test/pan-seared-salmon", "household_id": hid_a}
            )
            assert import_resp.status_code == 201
            recipe_data = import_resp.json()
            recipe_id = recipe_data["recipe_id"]

        # 3. Generate meal plan for Household A -> candidate pool includes the imported recipe
        plan_a_resp = await client.post(
            "/api/meal-plans/generate",
            json={"household_id": hid_a, "target_days": ["Monday"]}
        )
        assert plan_a_resp.status_code == 200
        plan_a = plan_a_resp.json()
        assert "Monday" in plan_a["meals"]
