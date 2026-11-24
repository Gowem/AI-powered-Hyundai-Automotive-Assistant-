"""Section, variant, vehicle and model-year detection via keyword rules."""

import re

from app.vehicles import count_vehicle_mentions, find_variants

SECTIONS = [
    "Specifications",
    "Engine & Performance",
    "Safety",
    "Comfort & Convenience",
    "Technology & Infotainment",
    "Exterior",
    "Interior",
    "Dimensions",
    "Variants & Features",
    "Colours",
    "Other",
]

_SECTION_KEYWORDS: dict[str, list[str]] = {
    "Specifications": [
        "specification",
        "specs",
        "technical",
        "kerb weight",
        "gross weight",
        "fuel tank",
        "suspension",
        "tyre",
        "tire",
        "brakes",
        "steering type",
    ],
    "Engine & Performance": [
        "engine",
        "displacement",
        "cc",
        "bhp",
        "ps",
        "kw",
        "torque",
        "nm",
        "turbo",
        "gdi",
        "crdi",
        "transmission",
        "dct",
        "ivt",
        "manual",
        "automatic",
        "mileage",
        "kmpl",
        "km/l",
        "fuel efficiency",
        "acceleration",
        "drive mode",
        "paddle shift",
        "petrol",
        "diesel",
        "cng",
        "battery",
        "range",
    ],
    "Safety": [
        "airbag",
        "abs",
        "esc",
        "vsm",
        "hac",
        "adas",
        "isofix",
        "safety",
        "collision",
        "lane",
        "blind",
        "tpms",
        "parking sensor",
        "camera",
        "brake assist",
        "seatbelt",
        "seat belt",
        "ncap",
        "dbc",
        "ebd",
    ],
    "Comfort & Convenience": [
        "ventilated",
        "climate",
        "air conditioning",
        "ac vents",
        "cruise control",
        "seat",
        "armrest",
        "sunroof",
        "wireless charger",
        "keyless",
        "push button",
        "comfort",
        "convenience",
        "power window",
        "boss mode",
        "cup holder",
        "rear ac",
    ],
    "Technology & Infotainment": [
        "infotainment",
        "touchscreen",
        "display",
        "bluelink",
        "connected",
        "apple carplay",
        "android auto",
        "speaker",
        "bose",
        "navigation",
        "ota",
        "alexa",
        "voice",
        "digital cluster",
        "usb",
        "type-c",
        "app",
        "smartwatch",
    ],
    "Exterior": [
        "exterior",
        "alloy",
        "wheel",
        "headlamp",
        "led",
        "drl",
        "tail lamp",
        "grille",
        "roof rail",
        "spoiler",
        "skid plate",
        "fog lamp",
        "door handle",
    ],
    "Interior": [
        "interior",
        "upholstery",
        "leather",
        "dashboard",
        "ambient",
        "cabin",
        "steering wheel",
        "trim",
        "inside door",
        "scuff plate",
    ],
    "Dimensions": [
        "dimension",
        "length",
        "width",
        "height",
        "wheelbase",
        "ground clearance",
        "boot space",
        "luggage",
        "turning radius",
        "mm",
    ],
    "Variants & Features": ["variant", "trim level", "feature list", "standard", "optional", "key features"],
    "Colours": ["colour", "color", "dual tone", "pearl", "metallic", "matte"],
}

_KW_PATTERNS = {
    sec: [re.compile(rf"(?<![a-z]){re.escape(k)}(?![a-z])") for k in kws] for sec, kws in _SECTION_KEYWORDS.items()
}


def detect_section(text: str, fallback: str | None = None, is_table: bool = False) -> str:
    low = text.lower()
    scores: dict[str, float] = {}
    for sec, pats in _KW_PATTERNS.items():
        score = sum(len(p.findall(low)) for p in pats)
        if score:
            scores[sec] = float(score)
    # explicit heading words weigh more
    for sec in SECTIONS:
        head = sec.split(" ")[0].lower()
        if re.search(rf"^\s*{re.escape(head)}", low, re.MULTILINE):
            scores[sec] = scores.get(sec, 0.0) + 3
    if is_table and scores.get("Engine & Performance", 0) + scores.get("Dimensions", 0) >= 4:
        scores["Specifications"] = scores.get("Specifications", 0.0) + 4
    if not scores:
        return fallback or "Other"
    return max(scores.items(), key=lambda kv: kv[1])[0]


def detect_variants(text: str, is_table: bool = False) -> list[str]:
    return find_variants(text, include_short=is_table)


def detect_vehicle(texts: list[str]) -> str | None:
    counts: dict[str, int] = {}
    for t in texts:
        for k, v in count_vehicle_mentions(t).items():
            counts[k] = counts.get(k, 0) + v
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


_YEAR = re.compile(r"(?<!\d)(20[2-3]\d)(?!\d)")


def detect_model_year(filename: str, first_pages: list[str]) -> str | None:
    m = _YEAR.search(filename)
    if m:
        return m.group(1)
    for t in first_pages:
        m2 = re.search(r"(?:model year|MY)\s*'?(20[2-3]\d)", t, re.IGNORECASE)
        if m2:
            return m2.group(1)
    return None
