import re
import unicodedata
from typing import Dict, Any, List, Optional
import httpx
from bs4 import BeautifulSoup

try:
    from recipe_scrapers import scrape_me
except ImportError:
    scrape_me = None

# Unicode fraction mapping
FRACTIONS = {
    '½': 0.5, '⅓': 1/3, '⅔': 2/3, '¼': 0.25, '¾': 0.75,
    '⅕': 0.2, '⅖': 0.4, '⅗': 0.6, '⅘': 0.8, '⅙': 1/6,
    '⅚': 5/6, '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875
}

UNIT_NORMALIZATION = {
    'lb': 'lbs', 'lbs': 'lbs', 'pound': 'lbs', 'pounds': 'lbs',
    'oz': 'oz', 'ounce': 'oz', 'ounces': 'oz',
    'cup': 'cups', 'cups': 'cups', 'c': 'cups',
    'tbsp': 'tbsp', 'tablespoon': 'tbsp', 'tablespoons': 'tbsp', 'tbs': 'tbsp',
    'tsp': 'tsp', 'teaspoon': 'tsp', 'teaspoons': 'tsp',
    'can': 'can', 'cans': 'can',
    'clove': 'count', 'cloves': 'count',
    'head': 'head', 'heads': 'head',
    'stalk': 'count', 'stalks': 'count',
    'sprig': 'count', 'sprigs': 'count',
    'fillet': 'count', 'fillets': 'count',
    'slice': 'count', 'slices': 'count',
    'pinch': 'tsp', 'pinches': 'tsp',
    'dash': 'tsp', 'dashes': 'tsp',
    'package': 'pkg', 'pkg': 'pkg',
    'bunch': 'bunch', 'bunches': 'bunch'
}

def parse_quantity(val_str: str) -> float:
    """Parses numeric string with fractions into float."""
    val_str = val_str.strip()
    # Check unicode fractions
    for u_char, u_val in FRACTIONS.items():
        if u_char in val_str:
            parts = val_str.split(u_char)
            whole = float(parts[0].strip()) if parts[0].strip().isdigit() else 0.0
            return round(whole + u_val, 2)

    # Check string fractions like '1 1/2' or '3/4'
    match_mixed = re.match(r'^(\d+)\s+(\d+)/(\d+)$', val_str)
    if match_mixed:
        whole = float(match_mixed.group(1))
        num = float(match_mixed.group(2))
        den = float(match_mixed.group(3))
        return round(whole + (num / den), 2)

    match_frac = re.match(r'^(\d+)/(\d+)$', val_str)
    if match_frac:
        num = float(match_frac.group(1))
        den = float(match_frac.group(2))
        return round(num / den, 2)

    # Check range like '2-3'
    match_range = re.match(r'^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)$', val_str)
    if match_range:
        return round((float(match_range.group(1)) + float(match_range.group(2))) / 2.0, 2)

    try:
        return round(float(val_str), 2)
    except ValueError:
        return 1.0

def parse_ingredient_line(raw_line: str) -> Dict[str, Any]:
    """
    Parses a raw ingredient string (e.g. '2 lbs boneless skinless chicken breasts, diced')
    into structured {name, quantity, unit}.
    """
    cleaned = raw_line.strip()
    if not cleaned:
        return {"name": "Ingredient", "quantity": 1.0, "unit": "count", "default_unit": "count"}

    # Pattern: [quantity/fraction] [unit] [ingredient name]
    # Replace unicode fractions first
    qty = 1.0
    unit = "count"

    tokens = cleaned.split()
    qty_tokens = []
    rest_tokens = []

    # Grep leading quantity components
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if (
            re.match(r'^\d+(?:\.\d+)?$', tok) or
            re.match(r'^\d+/\d+$', tok) or
            tok in FRACTIONS or
            re.match(r'^\d+[-–]\d+$', tok)
        ):
            qty_tokens.append(tok)
            idx += 1
        elif any(f in tok for f in FRACTIONS):
            qty_tokens.append(tok)
            idx += 1
        else:
            break

    if qty_tokens:
        qty = parse_quantity(" ".join(qty_tokens))
        rest_tokens = tokens[idx:]
    else:
        rest_tokens = tokens

    # Check if first rest token is a known unit
    name_tokens = rest_tokens
    if rest_tokens:
        first_word = re.sub(r'[^\w]', '', rest_tokens[0].lower())
        if first_word in UNIT_NORMALIZATION:
            unit = UNIT_NORMALIZATION[first_word]
            name_tokens = rest_tokens[1:]
        elif first_word in ('of',):
            name_tokens = rest_tokens[1:]

    raw_name = " ".join(name_tokens)
    # Clean up preparation instructions (e.g. ", minced", ", chopped", ", to taste")
    raw_name = re.sub(r',\s*(minced|chopped|diced|peeled|melted|thinly sliced|sliced|finely chopped|shredded|grated|to taste|softened|crushed).*$', '', raw_name, flags=re.IGNORECASE)
    raw_name = re.sub(r'\s*\([^)]*\)', '', raw_name) # Remove parentheticals
    raw_name = re.sub(r'\bto taste\b', '', raw_name, flags=re.IGNORECASE).strip(' ,.-')

    if not raw_name:
        raw_name = cleaned

    clean_title = " ".join(w.capitalize() for w in raw_name.split())

    return {
        "name": clean_title,
        "quantity": qty,
        "unit": unit,
        "default_unit": unit
    }

def infer_dietary_tags(title: str, description: str, ingredients: List[Dict[str, Any]], raw_keywords: Optional[List[str]] = None) -> List[str]:
    """Infers dietary tags from title, description, keywords, and ingredient names."""
    full_text = f"{title} {description} {' '.join(k for k in (raw_keywords or []))} "
    full_text += " ".join(i["name"] for i in ingredients)
    text_lower = full_text.lower()

    tags = set()

    # Direct keywords
    if "gluten-free" in text_lower or "gluten free" in text_lower:
        tags.add("gluten-free")
    if "dairy-free" in text_lower or "dairy free" in text_lower:
        tags.add("dairy-free")
    if "vegetarian" in text_lower:
        tags.add("vegetarian")
    if "vegan" in text_lower:
        tags.add("vegan")
    if "keto" in text_lower or "low-carb" in text_lower or "low carb" in text_lower:
        tags.add("keto")
    if "pescatarian" in text_lower:
        tags.add("pescatarian")
    if "high-protein" in text_lower or "high protein" in text_lower:
        tags.add("high-protein")

    # Negative inference
    gluten_indicators = ["wheat", "flour", "bread", "pasta", "soy sauce", "barley", "rye"]
    has_gluten = any(re.search(rf'\b{g}\b', text_lower) for g in gluten_indicators if g != "flour" or "almond flour" not in text_lower and "coconut flour" not in text_lower)
    if not has_gluten and "gluten-free" not in tags:
        tags.add("gluten-free")

    dairy_indicators = ["milk", "butter", "cheese", "cream", "yogurt", "parmesan", "cheddar", "mozzarella"]
    has_dairy = any(re.search(rf'\b{d}\b', text_lower) for d in dairy_indicators)
    if not has_dairy and "dairy-free" not in tags:
        tags.add("dairy-free")

    meat_indicators = ["chicken", "beef", "pork", "turkey", "bacon", "steak", "sausage", "ham"]
    fish_indicators = ["salmon", "cod", "tuna", "shrimp", "fish", "halibut", "tilapia", "trout", "crab", "lobster"]

    has_meat = any(re.search(rf'\b{m}\b', text_lower) for m in meat_indicators)
    has_fish = any(re.search(rf'\b{f}\b', text_lower) for f in fish_indicators)

    if not has_meat and not has_fish:
        tags.add("vegetarian")
    if has_fish and not has_meat:
        tags.add("pescatarian")
    if has_meat or has_fish or "eggs" in text_lower or "tofu" in text_lower:
        tags.add("high-protein")

    return sorted(list(tags))

async def extract_recipe_from_url(url: str) -> Dict[str, Any]:
    """
    Extracts recipe title, description, prep time, difficulty, structured ingredients,
    and instructions from an online URL using recipe-scrapers and Schema.org JSON-LD.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    # 1. Try recipe-scrapers if available
    if scrape_me:
        try:
            scraper = scrape_me(url)
            title = scraper.title()
            if title:
                description = scraper.description() or ""
                total_time = scraper.total_time() or 30
                raw_ingredients = scraper.ingredients() or []
                raw_instructions = scraper.instructions_list()
                if not raw_instructions and scraper.instructions():
                    raw_instructions = [s.strip() for s in scraper.instructions().split("\n") if s.strip()]

                structured_ingredients = [parse_ingredient_line(line) for line in raw_ingredients if line.strip()]
                keywords = []
                try:
                    kw = scraper.keywords()
                    if isinstance(kw, list):
                        keywords = kw
                    elif isinstance(kw, str):
                        keywords = [k.strip() for k in kw.split(",")]
                except Exception:
                    keywords = []

                difficulty = "quick" if total_time <= 20 else ("easy" if total_time <= 35 else ("medium" if total_time <= 60 else "hard"))
                tags = infer_dietary_tags(title, description, structured_ingredients, keywords)

                return {
                    "title": title.strip(),
                    "description": description.strip(),
                    "prep_time_minutes": total_time,
                    "difficulty_level": difficulty,
                    "ingredients": structured_ingredients,
                    "instructions": [{"step": i + 1, "text": t} for i, t in enumerate(raw_instructions)],
                    "dietary_tags": tags,
                    "source_url": url
                }
        except Exception:
            pass

    # 2. Fallback: Fetch raw HTML and parse JSON-LD
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")
    # Search for ld+json scripts
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    recipe_obj = None

    import json
    for script in json_ld_scripts:
        try:
            content = script.string or script.text
            if not content:
                continue
            data = json.loads(content)
            # Find Recipe
            if isinstance(data, dict):
                if data.get("@type") == "Recipe":
                    recipe_obj = data
                    break
                elif "@graph" in data and isinstance(data["@graph"], list):
                    for node in data["@graph"]:
                        if isinstance(node, dict) and node.get("@type") == "Recipe":
                            recipe_obj = node
                            break
            elif isinstance(data, list):
                for node in data:
                    if isinstance(node, dict) and node.get("@type") == "Recipe":
                        recipe_obj = node
                        break
        except Exception:
            continue
        if recipe_obj:
            break

    if recipe_obj:
        title = recipe_obj.get("name") or "Imported Recipe"
        description = recipe_obj.get("description") or ""
        raw_ings = recipe_obj.get("recipeIngredient") or []
        raw_inst = recipe_obj.get("recipeInstructions") or []

        inst_steps = []
        if isinstance(raw_inst, list):
            for it in raw_inst:
                if isinstance(it, str):
                    inst_steps.append(it.strip())
                elif isinstance(it, dict) and "text" in it:
                    inst_steps.append(it["text"].strip())
        elif isinstance(raw_inst, str):
            inst_steps = [s.strip() for s in raw_inst.split("\n") if s.strip()]

        structured_ingredients = [parse_ingredient_line(line) for line in raw_ings if line.strip()]
        tags = infer_dietary_tags(title, description, structured_ingredients)

        return {
            "title": title.strip(),
            "description": description.strip(),
            "prep_time_minutes": 30,
            "difficulty_level": "easy",
            "ingredients": structured_ingredients,
            "instructions": [{"step": i + 1, "text": t} for i, t in enumerate(inst_steps)],
            "dietary_tags": tags,
            "source_url": url
        }

    # 3. Final Fallback: OpenGraph tags
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    title = og_title["content"] if og_title and "content" in og_title.attrs else (soup.title.string if soup.title else "Online Recipe")
    desc = og_desc["content"] if og_desc and "content" in og_desc.attrs else ""

    return {
        "title": title.strip(),
        "description": desc.strip(),
        "prep_time_minutes": 30,
        "difficulty_level": "medium",
        "ingredients": [
            {"name": "Main Ingredient", "quantity": 1.0, "unit": "lbs", "default_unit": "lbs"}
        ],
        "instructions": [
            {"step": 1, "text": "Prepare recipe according to source guidelines."}
        ],
        "dietary_tags": ["high-protein"],
        "source_url": url
    }
