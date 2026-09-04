import os
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.models import MealPlan

DAY_OFFSETS = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

def escape_ics_text(text: Optional[str]) -> str:
    """Escapes special characters for RFC 5545 text values."""
    if not text:
        return ""
    # Backslash must be escaped first
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace(";", "\\;")
    escaped = escaped.replace(",", "\\,")
    # Newlines represented as \n
    escaped = escaped.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return escaped

def fold_line(line: str, max_length: int = 75) -> str:
    """Folds a line to adhere to RFC 5545 max 75 octets rule."""
    encoded = line.encode("utf-8")
    if len(encoded) <= max_length:
        return line

    parts = []
    current = bytearray()
    first = True

    for ch in line:
        ch_bytes = ch.encode("utf-8")
        limit = max_length if first else (max_length - 1)
        if len(current) + len(ch_bytes) > limit:
            parts.append(current.decode("utf-8"))
            current = bytearray(ch_bytes)
            first = False
        else:
            current.extend(ch_bytes)

    if current:
        parts.append(current.decode("utf-8"))

    return "\r\n ".join(parts)

def generate_ics_calendar(
    plan: MealPlan,
    household_name: Optional[str] = None,
    app_domain: Optional[str] = None
) -> str:
    """
    Generates an RFC 5545 compliant iCalendar string for a given MealPlan.
    Each scheduled meal item is represented as a dinner event at 6:00 PM UTC.
    """
    domain = app_domain or os.getenv("APP_DOMAIN", "https://splitbites.tbannon80-hp-mini.stream")
    if domain.endswith("/"):
        domain = domain[:-1]

    cal_name = f"{household_name}'s SplitBites Dinners" if household_name else "SplitBites Meal Plan"
    now_utc = datetime.now(timezone.utc)
    dtstamp = now_utc.strftime("%Y%m%dT%H%M%SZ")

    week_start = plan.week_start_date
    start_weekday = week_start.weekday()  # Monday = 0
    base_monday = week_start - timedelta(days=start_weekday)

    raw_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SplitBites//Meal Planning Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics_text(cal_name)}",
        "X-WR-CALDESC:SplitBites weekly dinner schedule and recipe guides",
        "X-WR-TIMEZONE:UTC",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]

    # Sort items by weekday order
    items = sorted(
        plan.items,
        key=lambda it: DAY_OFFSETS.get(it.day_of_week.capitalize(), 99)
    )

    for item in items:
        day_cap = item.day_of_week.capitalize()
        offset = DAY_OFFSETS.get(day_cap, 0)
        event_date = base_monday + timedelta(days=offset)
        date_str = event_date.strftime("%Y%m%d")

        dtstart = f"{date_str}T180000Z"
        dtend = f"{date_str}T190000Z"
        uid = f"splitbites-{plan.plan_id}-{day_cap.lower()}@splitbites.stream"

        recipe = item.recipe
        if recipe:
            title = recipe.title
            prep = f"{recipe.prep_time_minutes} minutes" if recipe.prep_time_minutes else "Quick prep"
            diff = recipe.difficulty_level if recipe.difficulty_level else "Easy"
            recipe_url = f"{domain}/#recipe-{recipe.recipe_id}"

            desc_parts = [
                f"Dinner: {title}",
                f"Prep time: {prep}",
                f"Difficulty: {diff}",
            ]
            if recipe.description:
                desc_parts.append(f"Notes: {recipe.description}")
            desc_parts.append(f"View in SplitBites: {recipe_url}")
            desc_text = "\n".join(desc_parts)
        else:
            title = f"Dinner ({day_cap})"
            desc_text = f"Scheduled dinner for {day_cap}. Check SplitBites for recipe updates.\nView in SplitBites: {domain}/"

        raw_lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:Dinner: {escape_ics_text(title)}",
            f"DESCRIPTION:{escape_ics_text(desc_text)}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ])

    raw_lines.append("END:VCALENDAR")

    folded_lines = [fold_line(line) for line in raw_lines]
    # RFC 5545 requires CRLF line terminators and trailing CRLF
    return "\r\n".join(folded_lines) + "\r\n"
