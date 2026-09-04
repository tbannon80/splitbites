import re
import json
import unicodedata
from typing import Dict, Any, List, Optional, Union
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
    # Weight
    'lb': 'lbs', 'lbs': 'lbs', 'pound': 'lbs', 'pounds': 'lbs',
    'oz': 'oz', 'ounce': 'oz', 'ounces': 'oz',
    'g': 'oz', 'gram': 'oz', 'grams': 'oz',
    'kg': 'lbs', 'kilogram': 'lbs', 'kilograms': 'lbs',

    # Volume
    'tbsp': 'tbsp', 'tablespoon': 'tbsp', 'tablespoons': 'tbsp', 'tbs': 'tbsp', 'tb': 'tbsp',
    'tsp': 'tsp', 'teaspoon': 'tsp', 'teaspoons': 'tsp',
    'cup': 'cups', 'cups': 'cups', 'c': 'cups',
    'fl oz': 'oz', 'fluid ounce': 'oz', 'fluid ounces': 'oz', 'floz': 'oz',
    'pint': 'cups', 'pints': 'cups', 'pt': 'cups',
    'quart': 'cups', 'quarts': 'cups', 'qt': 'cups',
    'gallon': 'cups', 'gallons': 'cups', 'gal': 'cups',
    'ml': 'cups', 'milliliter': 'cups', 'milliliters': 'cups',
    'l': 'cups', 'liter': 'cups', 'liters': 'cups',

    # Packaging / Counts
    'pinch': 'tsp', 'pinches': 'tsp',
    'dash': 'tsp', 'dashes': 'tsp',
    'can': 'can', 'cans': 'can',
    'clove': 'count', 'cloves': 'count',
    'head': 'head', 'heads': 'head',
    'stalk': 'count', 'stalks': 'count',
    'sprig': 'count', 'sprigs': 'count',
    'fillet': 'count', 'fillets': 'count',
    'slice': 'count', 'slices': 'count',
    'package': 'pkg', 'packages': 'pkg', 'pkg': 'pkg', 'pkgs': 'pkg',
    'bunch': 'bunch', 'bunches': 'bunch',
    'piece': 'count', 'pieces': 'count',
    'ea': 'count', 'each': 'count', 'item': 'count', 'items': 'count',
    'count': 'count', 'unit': 'count', 'units': 'count'
}

def parse_single_quantity(val_str: str) -> float:
    """Parses a single numeric string (integer, decimal, simple fraction, mixed fraction, or unicode fraction) into a float."""
    val_str = val_str.strip()
    if not val_str:
        return 1.0

    # 1. Unicode fractions (e.g. '½', '1 ½', '1½', '2 ¾')
    for u_char, u_val in FRACTIONS.items():
        if u_char in val_str:
            parts = val_str.split(u_char)
            whole_str = parts[0].strip().rstrip('-')
            try:
                whole = float(whole_str) if whole_str else 0.0
            except ValueError:
                whole = 0.0
            return round(whole + u_val, 3)

    # 2. Mixed string fraction (e.g. '1 1/2' or '1-1/2')
    match_mixed = re.match(r'^(\d+)(?:\s+|-)(\d+)/(\d+)$', val_str)
    if match_mixed:
        whole = float(match_mixed.group(1))
        num = float(match_mixed.group(2))
        den = float(match_mixed.group(3))
        if den != 0:
            return round(whole + (num / den), 3)

    # 3. Simple fraction (e.g. '3/4')
    match_frac = re.match(r'^(\d+)/(\d+)$', val_str)
    if match_frac:
        num = float(match_frac.group(1))
        den = float(match_frac.group(2))
        if den != 0:
            return round(num / den, 3)

    # 4. Standard float or integer
    try:
        return round(float(val_str), 3)
    except ValueError:
        return 1.0

def parse_quantity(val_str: str) -> float:
    """
    Parses numeric string with fractions or multi-token ranges into float.
    For ranges (e.g. '1-2', '1 - 2', '1 to 2'), parses as the ceiling (upper bound).
    """
    val_str = val_str.strip()
    if not val_str:
        return 1.0

    # Check for multi-token range: '1-2', '1 - 2', '1 to 2', '1–2', '1—2'
    # Avoid splitting '1-1/2' which is a mixed fraction (1 and 1/2)
    if not re.match(r'^\d+-\d+/\d+$', val_str):
        range_match = re.split(r'\s*(?:[-–—]|\bto\b)\s*', val_str, maxsplit=1)
        if len(range_match) == 2:
            p1_str, p2_str = range_match[0].strip(), range_match[1].strip()
            # If p2 has trailing units like '2 lbs', take just the numeric part
            p2_clean = re.split(r'\s+', p2_str)[0] if p2_str else ""
            if p1_str and p2_clean:
                v1 = parse_single_quantity(p1_str)
                v2 = parse_single_quantity(p2_clean)
                if v1 > 0 and v2 > 0:
                    # Ceiling: return the upper bound
                    return round(max(v1, v2), 2)

    return round(parse_single_quantity(val_str), 2)

def strip_non_ingredient_parentheticals(line: str) -> str:
    """
    Strips non-ingredient parenthetical text such as:
    - '(divided)'
    - '(optional)'
    - '(about 4 breasts)'
    - '(drained and rinsed)'
    - '(15 oz)' when preceded by a quantity (e.g. '1 (15 oz) can')
    If the line begins with a parenthesized measurement without leading quantity (e.g. '(15 oz) black beans'),
    unwraps the measurement so quantity/unit can be parsed.
    """
    s = line.strip()
    # Check if starts with parenthesized measurement without leading number, e.g. '(15 oz) black beans'
    m_lead = re.match(r'^\(([\d\s\./¼½¾⅓⅔⅛⅜⅝⅞-]+(?:\s*[a-zA-Z]+)?)\)\s+(.+)$', s)
    if m_lead:
        s = f"{m_lead.group(1)} {m_lead.group(2)}"

    # Strip any remaining parentheticals: (about 4 breasts), (divided), (15 oz), etc.
    s = re.sub(r'\s*\([^)]*\)', '', s)
    return s.strip()

def parse_ingredient_line(raw_line: str) -> Dict[str, Any]:
    """
    Parses a raw ingredient string (e.g. '1-2 lbs boneless skinless chicken breasts (about 4 breasts), diced')
    into structured {name, quantity, unit, default_unit}.
    """
    cleaned = raw_line.strip()
    if not cleaned:
        return {"name": "Ingredient", "quantity": 1.0, "unit": "count", "default_unit": "count"}

    # 1. Strip non-ingredient parentheticals first
    line = strip_non_ingredient_parentheticals(cleaned)

    # 2. Number pattern matching (handles unicode fractions, mixed fractions, decimals, integers)
    NUM_PATTERN = r'(?:\d+\s+(?:\d+/\d+|[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])|\d+-\d+/\d+|\d+[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]|\d+/\d+|[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]|\d+(?:\.\d+)?)'

    qty = 1.0
    remainder = line

    # Check for range first (e.g. '1-2 lbs', '1 - 2 lbs', '1 to 2 lbs') -> ceiling!
    range_regex = rf'^({NUM_PATTERN})\s*(?:[-–—]|\bto\b)\s*({NUM_PATTERN})(?:\s+|$)(.*)'
    m_range = re.match(range_regex, line, re.IGNORECASE)
    if m_range:
        q1_str = m_range.group(1)
        q2_str = m_range.group(2)
        remainder = m_range.group(3).strip()
        qty = parse_quantity(f"{q1_str} to {q2_str}")
    else:
        # Check for single quantity at start
        single_regex = rf'^({NUM_PATTERN})(?:\s+|$)(.*)'
        m_single = re.match(single_regex, line, re.IGNORECASE)
        if m_single:
            q_str = m_single.group(1)
            remainder = m_single.group(2).strip()
            qty = parse_quantity(q_str)

    # 3. Unit extraction
    unit = "count"
    # Check multi-word units like 'fl oz', 'fluid ounce'
    m_floz = re.match(r'^(fl(?:uid)?\.?\s*oz\.?|fluid\s+ounces?)\b\s*(.*)', remainder, re.IGNORECASE)
    if m_floz:
        unit = "oz"
        remainder = m_floz.group(2).strip()
    else:
        words = remainder.split()
        if words:
            first_word = re.sub(r'[^\w]', '', words[0].lower())
            if first_word in UNIT_NORMALIZATION:
                unit = UNIT_NORMALIZATION[first_word]
                remainder = " ".join(words[1:])

    # 4. Clean remainder of 'of' and preparation descriptors
    remainder = re.sub(r'^of\s+', '', remainder, flags=re.IGNORECASE).strip()

    # Clean preparation instructions from ingredient name
    remainder = re.sub(
        r',\s*(minced|chopped|diced|peeled|melted|thinly sliced|sliced|finely chopped|shredded|grated|to taste|softened|crushed|rinsed and drained|drained and rinsed|rinsed|drained|room temperature|divided|toasted).*$',
        '',
        remainder,
        flags=re.IGNORECASE
    )
    remainder = re.sub(r'\bto taste\b', '', remainder, flags=re.IGNORECASE).strip(' ,.-')

    if not remainder:
        remainder = cleaned

    clean_title = " ".join(w.capitalize() for w in remainder.split())

    return {
        "name": clean_title,
        "quantity": qty,
        "unit": unit,
        "default_unit": unit
    }

def parse_iso_duration(val: Any) -> int:
    """Parses ISO 8601 duration string (e.g. 'PT30M', 'PT1H15M') or integer minutes into integer minutes."""
    if not val:
        return 30
    if isinstance(val, (int, float)):
        return int(val)
    val_str = str(val).strip()
    if val_str.isdigit():
        return int(val_str)
    m = re.match(r'^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', val_str, re.IGNORECASE)
    if m:
        hours = int(m.group(1) or 0)
        minutes = int(m.group(2) or 0)
        total = hours * 60 + minutes
        return total if total > 0 else 30
    m_txt = re.search(r'(?:(\d+)\s*(?:hr|hour)s?)?\s*(?:(\d+)\s*(?:min|minute)s?)', val_str, re.IGNORECASE)
    if m_txt:
        h = int(m_txt.group(1) or 0)
        m_ = int(m_txt.group(2) or 0)
        total = h * 60 + m_
        if total > 0:
            return total
    return 30

def parse_nutrition_dict(nutrition_data: Any) -> Dict[str, Any]:
    """
    Parses Schema.org nutrition information (calories, proteinContent, carbohydrateContent, fatContent)
    into standard numeric fields:
    - calories: float or int
    - protein_g: float
    - carbs_g: float
    - fat_g: float
    """
    if not isinstance(nutrition_data, dict):
        return {}

    def extract_num(val: Any) -> Optional[float]:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return round(float(val), 1)
        m = re.search(r'(\d+(?:\.\d+)?)', str(val))
        if m:
            try:
                return round(float(m.group(1)), 1)
            except ValueError:
                return None
        return None

    calories = extract_num(nutrition_data.get("calories"))
    protein = extract_num(
        nutrition_data.get("proteinContent")
        or nutrition_data.get("protein_g")
        or nutrition_data.get("protein")
    )
    carbs = extract_num(
        nutrition_data.get("carbohydrateContent")
        or nutrition_data.get("carbs_g")
        or nutrition_data.get("carbohydrates")
    )
    fat = extract_num(
        nutrition_data.get("fatContent")
        or nutrition_data.get("fat_g")
        or nutrition_data.get("fat")
    )

    res = {}
    if calories is not None:
        res["calories"] = round(calories) if calories.is_integer() else calories
    if protein is not None:
        res["protein_g"] = protein
    if carbs is not None:
        res["carbs_g"] = carbs
    if fat is not None:
        res["fat_g"] = fat

    return res

def infer_dietary_tags(title: str, description: str, ingredients: List[Dict[str, Any]], raw_keywords: Optional[List[str]] = None) -> List[str]:
    """Infers dietary tags from title, description, keywords, and ingredient names."""
    full_text = f"{title} {description} {' '.join(k for k in (raw_keywords or []))} "
    full_text += " ".join(i.get("name", "") for i in ingredients)
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
    has_gluten = any(re.search(rf'\b{g}\b', text_lower) for g in gluten_indicators if g != "flour" or ("almond flour" not in text_lower and "coconut flour" not in text_lower))
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

def parse_recipe_from_html_heuristics(soup: BeautifulSoup, url: str) -> Optional[Dict[str, Any]]:
    """
    Tier-2 HTML Heuristic Fallback Parser:
    Extracts recipe title, summary, prep/cook time, ingredients, instructions,
    and dietary tags by targeting common food blog classes (WPRM, Tasty Recipes,
    EasyRecipe, Create by Mediavine, and generic recipe cards).
    """
    # 1. Title Extraction
    title = None
    title_selectors = [
        ".wprm-recipe-name",
        ".tasty-recipes-title",
        ".ERSName",
        ".mv-create-title",
        ".recipe-title",
        ".recipe__title",
        "h1.entry-title",
        "h2.wprm-recipe-header",
        "h1",
        "h2.recipe-name"
    ]
    for sel in title_selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(" ", strip=True)
            break

    if not title:
        og_t = soup.find("meta", property="og:title")
        if og_t and og_t.get("content"):
            title = og_t["content"].strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()

    if not title or len(title) < 2:
        return None

    # 2. Description Extraction
    description = ""
    desc_selectors = [
        ".wprm-recipe-summary",
        ".tasty-recipes-description",
        ".tasty-recipes-summary",
        ".ERSSummary",
        ".mv-create-description",
        ".recipe-summary",
        ".recipe__summary"
    ]
    for sel in desc_selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            description = el.get_text(" ", strip=True)
            break

    if not description:
        og_d = soup.find("meta", property="og:description")
        if og_d and og_d.get("content"):
            description = og_d["content"].strip()

    # 3. Prep Time / Total Time Extraction
    prep_time = 30
    time_selectors = [
        ".wprm-recipe-total-time",
        ".wprm-recipe-prep-time",
        ".tasty-recipes-total-time",
        ".tasty-recipes-prep-time",
        ".ERSTotalTime",
        ".ERSTime",
        ".mv-create-time"
    ]
    for sel in time_selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            t_text = el.get_text(" ", strip=True)
            parsed_t = parse_iso_duration(t_text)
            if parsed_t > 0:
                prep_time = parsed_t
                break

    # 4. Ingredient Extraction
    ingredient_selectors = [
        ".wprm-recipe-ingredient",
        ".wprm-recipe-ingredients li",
        ".tasty-recipes-ingredients li",
        ".tasty-recipe-ingredients li",
        ".easyrecipe .ingredient",
        ".easyrecipe .ERSIngredients li",
        ".ERSIngredients li",
        ".mv-create-ingredients li",
        "li[itemprop='recipeIngredient']",
        "span[itemprop='recipeIngredient']",
        ".recipe-ingredients li",
        ".recipe__ingredients li",
        ".ingredients li",
        "ul.ingredients li",
        "ol.ingredients li"
    ]

    raw_ingredient_lines = []
    for sel in ingredient_selectors:
        items = soup.select(sel)
        if items:
            for it in items:
                # Skip headings or group labels
                if "group-name" in it.get("class", []) or "heading" in it.get("class", []):
                    continue
                txt = it.get_text(" ", strip=True)
                # Clean multiple spaces
                txt = " ".join(txt.split())
                if txt and len(txt) > 2 and not txt.endswith(":"):
                    raw_ingredient_lines.append(txt)
            if raw_ingredient_lines:
                break

    if not raw_ingredient_lines:
        return None

    structured_ingredients = [parse_ingredient_line(l) for l in raw_ingredient_lines if l.strip()]
    if not structured_ingredients:
        return None

    # 5. Instructions Extraction
    instruction_selectors = [
        ".wprm-recipe-instruction",
        ".wprm-recipe-instructions li",
        ".tasty-recipes-instructions li",
        ".tasty-recipe-instructions li",
        ".easyrecipe .instruction",
        ".easyrecipe .ERSInstructions li",
        ".ERSInstructions li",
        ".mv-create-instructions li",
        "li[itemprop='recipeInstructions']",
        ".recipe-instructions li",
        ".recipe__instructions li",
        ".instructions li",
        ".directions li",
        "ol.instructions li",
        "ul.instructions li"
    ]

    raw_instruction_lines = []
    for sel in instruction_selectors:
        items = soup.select(sel)
        if items:
            for it in items:
                txt = it.get_text(" ", strip=True)
                txt = " ".join(txt.split())
                if txt and len(txt) > 3 and not txt.endswith(":"):
                    raw_instruction_lines.append(txt)
            if raw_instruction_lines:
                break

    if not raw_instruction_lines:
        raw_instruction_lines = ["Prepare and cook ingredients according to standard recipe directions."]

    instructions = [{"step": i + 1, "text": t} for i, t in enumerate(raw_instruction_lines)]
    # Nutrition Extraction in HTML heuristics
    nutrition = {}
    nutr_container = soup.select_one(".wprm-recipe-nutrition-container, .tasty-recipes-nutrition, .mv-create-nutrition, [itemprop='nutrition']")
    if nutr_container:
        txt = nutr_container.get_text(" ", strip=True)
        m_cal = re.search(r'calories[:\s]*(\d+)', txt, re.IGNORECASE)
        m_prot = re.search(r'protein[:\s]*(\d+(?:\.\d+)?)\s*g?', txt, re.IGNORECASE)
        m_carb = re.search(r'(?:carbohydrates|carbs)[:\s]*(\d+(?:\.\d+)?)\s*g?', txt, re.IGNORECASE)
        m_fat = re.search(r'fat[:\s]*(\d+(?:\.\d+)?)\s*g?', txt, re.IGNORECASE)
        if m_cal: nutrition["calories"] = int(m_cal.group(1))
        if m_prot: nutrition["protein_g"] = float(m_prot.group(1))
        if m_carb: nutrition["carbs_g"] = float(m_carb.group(1))
        if m_fat: nutrition["fat_g"] = float(m_fat.group(1))

    difficulty = "quick" if prep_time <= 20 else ("easy" if prep_time <= 35 else ("medium" if prep_time <= 60 else "hard"))
    tags = infer_dietary_tags(title, description, structured_ingredients)

    return {
        "title": title.strip(),
        "description": description.strip(),
        "prep_time_minutes": prep_time,
        "difficulty_level": difficulty,
        "ingredients": structured_ingredients,
        "instructions": instructions,
        "nutrition_per_serving": nutrition,
        "dietary_tags": tags,
        "source_url": url
    }

async def extract_recipe_from_url(url: str) -> Dict[str, Any]:
    """
    Extracts recipe title, description, prep time, difficulty, structured ingredients,
    and instructions from an online URL.
    - Tier 1: Schema.org JSON-LD microdata (and recipe-scrapers if supported).
    - Tier 2: HTML heuristic fallback parsing using BeautifulSoup targeting common food blog classes
              (wprm-recipe, tasty-recipes, easyrecipe, mv-create, etc.).
    - If both fail, raises ValueError leading to HTTP 422 Unprocessable Entity.
    """
    clean_url = url.strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        raise ValueError(f"Invalid URL format: '{clean_url}'. URL must begin with http:// or https://")

    # 1. Fetch HTML content
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(clean_url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        raise ValueError(f"Could not fetch URL '{clean_url}': {str(e)}")

    # 2. Tier 1: recipe-scrapers library (if domain supported and yields ingredients)
    if scrape_me:
        try:
            scraper = scrape_me(clean_url, html=html)
            raw_ingredients = scraper.ingredients() or []
            if raw_ingredients:
                title = scraper.title() or "Imported Recipe"
                description = scraper.description() or ""
                total_time = scraper.total_time() or 30
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

                nutrition = {}
                try:
                    if hasattr(scraper, "nutrients"):
                        raw_nutrients = scraper.nutrients()
                        if raw_nutrients:
                            nutrition = parse_nutrition_dict(raw_nutrients)
                except Exception:
                    nutrition = {}

                return {
                    "title": title.strip(),
                    "description": description.strip(),
                    "prep_time_minutes": total_time,
                    "difficulty_level": difficulty,
                    "ingredients": structured_ingredients,
                    "instructions": [{"step": i + 1, "text": t} for i, t in enumerate(raw_instructions)],
                    "nutrition_per_serving": nutrition,
                    "dietary_tags": tags,
                    "source_url": clean_url
                }
        except Exception:
            pass

    soup = BeautifulSoup(html, "html.parser")

    # 3. Tier 1 (Schema.org JSON-LD microdata)
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    recipe_obj = None

    for script in json_ld_scripts:
        try:
            content = script.string or script.text
            if not content:
                continue
            data = json.loads(content)
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

    # If Recipe JSON-LD found and has recipeIngredient
    if recipe_obj and recipe_obj.get("recipeIngredient"):
        raw_ings = recipe_obj.get("recipeIngredient") or []
        if isinstance(raw_ings, list) and len(raw_ings) > 0:
            title = recipe_obj.get("name") or "Imported Recipe"
            description = recipe_obj.get("description") or ""
            raw_inst = recipe_obj.get("recipeInstructions") or []
            total_time = parse_iso_duration(recipe_obj.get("totalTime") or recipe_obj.get("prepTime"))

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
            difficulty = "quick" if total_time <= 20 else ("easy" if total_time <= 35 else ("medium" if total_time <= 60 else "hard"))

            raw_nutrition = recipe_obj.get("nutrition")
            nutrition = parse_nutrition_dict(raw_nutrition)

            return {
                "title": title.strip(),
                "description": description.strip(),
                "prep_time_minutes": total_time,
                "difficulty_level": difficulty,
                "ingredients": structured_ingredients,
                "instructions": [{"step": i + 1, "text": t} for i, t in enumerate(inst_steps)],
                "nutrition_per_serving": nutrition,
                "dietary_tags": tags,
                "source_url": clean_url
            }

    # 4. Tier 2: HTML heuristic fallback parsing using BeautifulSoup
    heuristic_recipe = parse_recipe_from_html_heuristics(soup, clean_url)
    if heuristic_recipe and heuristic_recipe.get("ingredients"):
        return heuristic_recipe

    # 5. Both failed -> Raise descriptive ValueError leading to HTTP 422
    raise ValueError(f"Could not extract recipe from URL '{clean_url}'. The page does not contain valid recipe microdata or recognizable recipe elements.")
