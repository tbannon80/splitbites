import re
from typing import List, Dict, Any, Union

TIMER_REGEX = re.compile(
    r"(?:(?:for|about|another|approx(?:\.|imately)?)\s+)?(\d+(?:\.\d+)?(?:\s*(?:-|–|to)\s*\d+(?:\.\d+)?)?)\s*(mins?|minutes?|hours?|hrs?)\b",
    re.IGNORECASE
)

def extract_timer_durations(text: str) -> List[Dict[str, Any]]:
    """
    Scans instruction text for cooking time intervals (e.g., "simmer for 15 minutes",
    "bake 25-30 mins", "rest for 5 minutes", "roast for 1.5 hours") and returns
    structured timer metadata with duration in minutes and seconds.
    """
    if not text:
        return []

    matches = TIMER_REGEX.finditer(text)
    timers = []
    seen = set()

    for m in matches:
        raw_val = m.group(1).strip()
        unit_str = m.group(2).lower()
        nums = re.findall(r"\d+(?:\.\d+)?", raw_val)
        if not nums:
            continue

        base_num = float(nums[0])
        is_hour = unit_str.startswith("h")
        minutes = round(base_num * 60) if is_hour else round(base_num)
        total_seconds = minutes * 60

        label = f"{base_num:g}h" if is_hour else f"{round(base_num)}m"
        key = (minutes, total_seconds)
        if key in seen:
            continue
        seen.add(key)

        timers.append({
            "label": label,
            "minutes": minutes,
            "seconds": total_seconds,
            "raw_text": m.group(0).strip(),
            "range": raw_val
        })

    return timers

def normalize_instruction_steps(raw_instructions: Union[List[Any], str]) -> List[Dict[str, Any]]:
    """
    Normalizes instruction steps from either JSON step arrays, list of strings,
    or raw newline-delimited text into standard list of {"step": int, "text": str}.
    """
    if not raw_instructions:
        return []

    if isinstance(raw_instructions, str):
        lines = [l.strip() for l in raw_instructions.split("\n") if l.strip()]
        return [{"step": i + 1, "text": l.lstrip("0123456789.- ")} for i, l in enumerate(lines)]

    elif isinstance(raw_instructions, list):
        steps = []
        for i, item in enumerate(raw_instructions):
            if isinstance(item, str):
                steps.append({"step": i + 1, "text": item.strip()})
            elif isinstance(item, dict):
                text_val = item.get("text") or item.get("instruction") or ""
                steps.append({"step": item.get("step", i + 1), "text": text_val.strip()})
            elif hasattr(item, "text"):
                steps.append({"step": getattr(item, "step", i + 1), "text": getattr(item, "text", "").strip()})
        return steps

    return []
