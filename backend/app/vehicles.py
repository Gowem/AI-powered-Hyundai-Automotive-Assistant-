"""Known Hyundai model NAMES and aliases.

This module intentionally contains names only. It must never contain specifications,
features, prices or any other vehicle facts. All facts come from uploaded brochures.
"""

import re

OTHER = "Other"

# canonical name -> aliases (lowercase). Misspellings are included for fuzzy user input.
VEHICLE_ALIASES: dict[str, list[str]] = {
    "Alcazar": ["alcazar", "alcazr", "alcaza", "alkazar", "alcazaar"],
    "Creta": ["creta", "creata", "kreta", "creta n line", "creta electric"],
    "i20": ["i20", "i-20", "i 20", "i20 n line", "elite i20"],
    "Aura": ["aura", "grand i10 aura"],
    "Venue": ["venue", "venu", "venue n line"],
    "Verna": ["verna", "varna"],
    "Exter": ["exter", "extor"],
    "Grand i10 Nios": ["grand i10 nios", "i10 nios", "nios", "grand i10", "i10"],
    "Tucson": ["tucson", "tuscon", "tucsan"],
    "Ioniq 5": ["ioniq 5", "ioniq5", "ioniq"],
    "Kona Electric": ["kona electric", "kona"],
}

KNOWN_MODELS: list[str] = list(VEHICLE_ALIASES.keys())

# Generic variant tokens used for retrieval boosts only (never as facts).
VARIANT_TOKENS: list[str] = [
    "SX(O) Tech",
    "SX Tech",
    "SX(O)",
    "S(O)+",
    "S(O)",
    "SX",
    "EX",
    "Executive",
    "Prestige",
    "Platinum",
    "Signature",
    "Knight",
    "Adventure",
    "Corporate",
    "Asta",
    "Sportz",
    "Magna",
    "Era",
    "Kappa",
    "N Line",
    "S",
    "E",
]

_SORTED_ALIASES: list[tuple[str, str]] = sorted(
    ((alias, canon) for canon, aliases in VEHICLE_ALIASES.items() for alias in [canon.lower(), *aliases]),
    key=lambda p: -len(p[0]),
)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias).replace(r"\ ", r"[\s\-_]*")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)


_ALIAS_PATTERNS: list[tuple[re.Pattern[str], str]] = [(_alias_pattern(a), c) for a, c in _SORTED_ALIASES]


def normalise_vehicle(name: str | None) -> str | None:
    """Map a user-supplied name ("hyundai alcazr") to a canonical model, or None."""
    if not name:
        return None
    cleaned = re.sub(r"\bhyundai\b", "", name, flags=re.IGNORECASE).strip().lower()
    if not cleaned:
        return None
    for canon in KNOWN_MODELS:
        if cleaned == canon.lower():
            return canon
    for alias, canon in _SORTED_ALIASES:
        if cleaned == alias:
            return canon
    found = find_vehicles(cleaned)
    return found[0] if found else None


def find_vehicles(text: str) -> list[str]:
    """Return canonical models mentioned in text, in order of first appearance."""
    hits: dict[str, int] = {}
    consumed: list[tuple[int, int]] = []
    for pattern, canon in _ALIAS_PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in consumed):
                continue
            consumed.append(span)
            hits[canon] = min(hits.get(canon, m.start()), m.start())
    return [c for c, _ in sorted(hits.items(), key=lambda kv: kv[1])]


def count_vehicle_mentions(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    consumed: list[tuple[int, int]] = []
    for pattern, canon in _ALIAS_PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in consumed):
                continue
            consumed.append(span)
            counts[canon] = counts.get(canon, 0) + 1
    return counts


def detect_from_filename(filename: str) -> str | None:
    stem = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    stem = re.sub(r"[_\-.]+", " ", stem)
    found = find_vehicles(stem)
    return found[0] if found else None


_VARIANT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"(?<![A-Za-z0-9(]){re.escape(v).replace(r'\ ', r'\s+')}(?![A-Za-z0-9)])"), v) for v in VARIANT_TOKENS
]
# Single-letter variants are only trustworthy in table-ish contexts; require surrounding pipes/columns.
_SHORT_VARIANTS = {"S", "E"}


def find_variants(text: str, include_short: bool = False) -> list[str]:
    found: list[str] = []
    consumed: list[tuple[int, int]] = []
    for pattern, name in _VARIANT_PATTERNS:
        if name in _SHORT_VARIANTS and not include_short:
            continue
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in consumed):
                continue
            consumed.append(span)
            if name not in found:
                found.append(name)
    return found
