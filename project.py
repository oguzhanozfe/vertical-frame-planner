"""Place a portrait crop around annotated subjects in a landscape shot."""

import math


def items(data, key, *, allow_empty=False):
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, list) or (not value and not allow_empty) or len(value) > 500:
        raise ValueError(f"{key} must be a list of up to 500 entries")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Every entry in {key} must be an object")
    return value


def number(value, field, *, positive=False):
    if type(value) not in (int, float) or not 0 <= value <= 1e12 or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite nonnegative number at most 1e12")
    if positive and value == 0:
        raise ValueError(f"{field} must be greater than zero")
    return value


def label(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")
    return value.strip()


TITLE = "Vertical Frame Planner"
DESCRIPTION = "Plan exact 9:16 crops for landscape footage and flag subjects outside the safe area."
PROMPT = "Create a shot-by-shot reframing note. Report pixel offsets and name the subjects outside safe margins. Suggest a split shot or alternate source when one crop cannot contain the required subjects."


def pixels(value, field):
    if type(value) is not int or not 1 <= value <= 100_000:
        raise ValueError(f"{field} must be an integer from 1 to 100,000")
    return value


def offset(low, high, source, crop, margin):
    # Both edge constraints must hold at an integer crop origin.
    first = max(0, math.ceil(high - crop * (1 - margin) - 1e-9))
    last = min(source - crop, math.floor(low - crop * margin + 1e-9))
    preferred = round((low + high - crop) / 2)
    if first <= last:
        return min(last, max(first, preferred))
    return max(0, min(source - crop, preferred))


def analyze(data: dict) -> dict:
    shots = items(data, "shots")
    width = pixels(data.get("source_width"), "source_width")
    height = pixels(data.get("source_height"), "source_height")
    margin = number(data.get("safe_margin", 0.05), "safe_margin")
    if width <= height or height < 16 or margin >= 0.5:
        raise ValueError("Use a landscape source at least 16 pixels high and a margin below 0.5")
    units = min(width // 9, height // 16)
    cw, ch = 9 * units, 16 * units
    rows = []
    needs_review = 0
    seen = set()
    for shot in shots:
        name = label(shot.get("name"), "shot name")
        if name in seen:
            raise ValueError("Shot names must be unique")
        seen.add(name)
        boxes = []
        for subject in items(shot, "subjects"):
            who = label(subject.get("name"), "subject name")
            x, y = number(subject.get("x"), "x"), number(subject.get("y"), "y")
            w, h = number(subject.get("width"), "width", positive=True), number(subject.get("height"), "height", positive=True)
            if x + w > width or y + h > height:
                raise ValueError(f"Subject outside source bounds: {who}")
            boxes.append((x, y, x + w, y + h, who))
        left = offset(min(b[0] for b in boxes), max(b[2] for b in boxes), width, cw, margin)
        top = offset(min(b[1] for b in boxes), max(b[3] for b in boxes), height, ch, margin)
        outside = [who for x, y, r, b, who in boxes
                   if x < left + cw * margin - 1e-9 or r > left + cw * (1 - margin) + 1e-9
                   or y < top + ch * margin - 1e-9 or b > top + ch * (1 - margin) + 1e-9]
        if outside:
            needs_review += 1
        rows.append({"Shot": name, "Left (px)": left, "Top (px)": top, "Width (px)": cw, "Height (px)": ch,
                     "Outside safe area": ", ".join(outside) or "None"})
    return {"summary": f"{len(rows) - needs_review} of {len(rows)} shots keep every annotated subject inside the safe area.",
            "metrics": {"Shots": len(rows), "Need reframing": needs_review, "Crop size": f"{cw} × {ch}"}, "rows": rows}
