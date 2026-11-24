"""Query understanding: turn a message (+ history) into a validated QueryPlan."""

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.llm.base import ChatMessage, LLMProvider
from app.rag.prompts import INTENT_SYSTEM
from app.vehicles import KNOWN_MODELS, find_variants, find_vehicles, normalise_vehicle

logger = logging.getLogger("app.rag")

Intent = Literal[
    "feature_list", "model_comparison", "variant_comparison", "recommendation", "spec_lookup", "general", "out_of_scope"
]
DEFAULT_COMPARISON_ASPECTS = ["engine", "safety", "comfort", "technology", "performance", "dimensions"]

ASPECT_QUERY_TERMS: dict[str, str] = {
    "engine": "engine displacement power torque transmission fuel type",
    "performance": "performance power torque drive modes acceleration",
    "safety": "safety airbags ADAS ABS ESC brakes camera sensors",
    "comfort": "comfort convenience seats ventilated climate control sunroof",
    "technology": "technology infotainment touchscreen display connected car speakers",
    "dimensions": "dimensions length width height wheelbase boot space ground clearance",
    "fuel_efficiency": "fuel efficiency mileage kmpl ARAI",
    "price": "price ex-showroom",
    "exterior": "exterior design alloy wheels headlamps LED",
    "interior": "interior cabin upholstery dashboard ambient lighting",
    "colours": "colours paint dual tone",
    "variants": "variants trims features by variant",
}


class Requirements(BaseModel):
    seating: int | None = None
    fuel: str | None = None
    transmission: str | None = None
    usage: str | None = None
    budget: str | None = None
    priorities: list[str] = Field(default_factory=list)

    @field_validator("seating", mode="before")
    @classmethod
    def _seat(cls, v: Any) -> Any:
        if isinstance(v, str):
            m = re.search(r"\d+", v)
            return int(m.group()) if m else None
        return v


class QueryPlan(BaseModel):
    intent: Intent = "general"
    vehicles: list[str] = Field(default_factory=list)
    variants: dict[str, list[str]] = Field(default_factory=dict)
    aspects: list[str] = Field(default_factory=list)
    requirements: Requirements = Field(default_factory=Requirements)
    sub_queries: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarifying_question: str | None = None
    source: Literal["llm", "heuristic"] = "llm"

    @field_validator("requirements", mode="before")
    @classmethod
    def _req(cls, v: Any) -> Any:
        return v or {}

    @field_validator("variants", mode="before")
    @classmethod
    def _var(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            return {}
        return {k: [str(x) for x in (vals or [])] for k, vals in v.items() if isinstance(vals, list)}


_COMPARE = re.compile(r"\b(vs\.?|versus|compare|comparison|difference|differ|better than|or the)\b", re.I)
_RECOMMEND = re.compile(
    r"\b(which (one )?(should|would|is better)|recommend|suggest|better for|best for|suit|should i (buy|get|choose)|"
    r"family of|i need|i want|looking for|my budget)\b",
    re.I,
)
_FEATURES = re.compile(r"\b(features?|list|highlights|what does .* offer|tell me about)\b", re.I)
_VARIANT = re.compile(r"\b(variants?|trims?)\b", re.I)
_AUTO = re.compile(
    r"\b(car|cars|suv|sedan|hatchback|vehicle|engine|mileage|safety|airbag|hyundai|variant|brochure|boot|seat|"
    r"price|torque|power|diesel|petrol|cng|ev|electric|transmission|automatic|manual|feature|adas|sunroof|drive|"
    r"interior|exterior|colour|color|dimension|spec|specs|warranty|service)\b",
    re.I,
)
_FOLLOWUP = re.compile(r"\b(it|its|it's|this car|that car|this one|that one|both|them|they|their|the same)\b", re.I)


def _aspects_from_text(text: str) -> list[str]:
    low = text.lower()
    found: list[str] = []
    rules = {
        "engine": ["engine", "power", "torque", "displacement", "cc", "bhp", "transmission"],
        "safety": ["safety", "airbag", "adas", "abs", "ncap", "isofix", "camera"],
        "comfort": ["comfort", "seat", "ventilated", "sunroof", "climate", "space"],
        "technology": ["technology", "tech", "infotainment", "screen", "connected", "carplay", "android"],
        "performance": ["performance", "acceleration", "drive mode"],
        "dimensions": ["dimension", "boot", "length", "width", "wheelbase", "ground clearance", "size"],
        "fuel_efficiency": ["mileage", "fuel efficiency", "kmpl", "economy"],
        "price": ["price", "cost", "on-road", "ex-showroom", "budget"],
        "exterior": ["exterior", "alloy", "headlamp", "design"],
        "interior": ["interior", "cabin", "upholstery"],
        "colours": ["colour", "color"],
    }
    for aspect, kws in rules.items():
        if any(k in low for k in kws):
            found.append(aspect)
    return found


def _history_vehicles(history: list[ChatMessage]) -> list[str]:
    for m in reversed(history):
        if m.role == "user":
            v = find_vehicles(m.content)
            if v:
                return v
    for m in reversed(history):
        v = find_vehicles(m.content)
        if v:
            return v[:2]
    return []


def heuristic_plan(message: str, history: list[ChatMessage]) -> QueryPlan:
    vehicles = find_vehicles(message)
    off_topic = not vehicles and not _AUTO.search(message) and not _FOLLOWUP.search(message)
    if not vehicles and not off_topic:
        vehicles = _history_vehicles(history)
    aspects = _aspects_from_text(message)
    variants_found = find_variants(message, include_short=False)

    if off_topic:
        intent: Intent = "out_of_scope"
    elif _RECOMMEND.search(message) and (len(vehicles) != 1 or "or" in message.lower().split()):
        intent = "recommendation"
    elif _VARIANT.search(message) and len(vehicles) <= 1 and (_COMPARE.search(message) or variants_found):
        intent = "variant_comparison"
    elif len(variants_found) >= 2 and len(vehicles) <= 1:
        intent = "variant_comparison"
    elif _COMPARE.search(message) and len(vehicles) >= 2:
        intent = "model_comparison"
    elif _FEATURES.search(message):
        intent = "feature_list"
    elif aspects and vehicles:
        intent = "spec_lookup"
    else:
        intent = "general"
    variants = {vehicles[0]: variants_found} if vehicles and variants_found else {}
    plan = QueryPlan(intent=intent, vehicles=vehicles, variants=variants, aspects=aspects, source="heuristic")
    req = plan.requirements
    low = message.lower()
    if m := re.search(r"family of (\d+)|(\d+)\s*(?:seater|seats|people|members)", low):
        req.seating = int(m.group(1) or m.group(2))
    for fuel in ("diesel", "petrol", "cng", "electric"):
        if fuel in low:
            req.fuel = fuel
    if "automatic" in low or re.search(r"\bauto\b", low):
        req.transmission = "automatic"
    elif "manual" in low:
        req.transmission = "manual"
    for usage in ("city", "highway", "long drive", "off-road"):
        if usage in low:
            req.usage = usage
    return plan


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("plan is not an object")
    return data


def finalise_plan(plan: QueryPlan, message: str, history: list[ChatMessage]) -> QueryPlan:
    # normalise + dedupe vehicles; keep unknown-but-named models (e.g. Tucson) via aliases only
    seen: list[str] = []
    for v in plan.vehicles:
        canon = normalise_vehicle(v)
        if canon and canon not in seen:
            seen.append(canon)
    for v in find_vehicles(message):
        if v not in seen:
            seen.append(v)
    if not seen and plan.intent != "out_of_scope" and _FOLLOWUP.search(message):
        seen = _history_vehicles(history)
    plan.vehicles = seen
    plan.variants = {
        normalise_vehicle(k) or k: v for k, v in plan.variants.items() if (normalise_vehicle(k) or k) in seen and v
    }
    if plan.intent in ("model_comparison", "variant_comparison", "recommendation") and not plan.aspects:
        plan.aspects = list(DEFAULT_COMPARISON_ASPECTS)
    if plan.intent == "feature_list" and not plan.aspects:
        plan.aspects = ["engine", "safety", "comfort", "technology", "exterior", "interior"]
    if plan.intent == "variant_comparison" and "variants" not in plan.aspects:
        plan.aspects.append("variants")
    # make sure every vehicle x aspect has a sub-query
    queries = [q.strip() for q in plan.sub_queries if isinstance(q, str) and q.strip()][:12]
    for v in plan.vehicles or [""]:
        variants = " ".join(plan.variants.get(v, []))
        aspects = plan.aspects or [""]
        for a in aspects:
            if not any(v.lower() in q.lower() and a.split("_")[0] in q.lower() for q in queries):
                q = " ".join(x for x in (v, variants, ASPECT_QUERY_TERMS.get(a, a)) if x).strip()
                if q:
                    queries.append(q)
    if not queries:
        queries = [message]
    queries.insert(0, message)  # the raw question always participates
    plan.sub_queries = list(dict.fromkeys(queries))[:16]
    return plan


async def plan_query(provider: LLMProvider, message: str, history: list[ChatMessage]) -> QueryPlan:
    convo = "\n".join(f"{m.role.upper()}: {m.content[:600]}" for m in history[-6:])
    prompt = f"CONVERSATION HISTORY:\n{convo or '(none)'}\n\nCURRENT MESSAGE:\n{message}"
    system = INTENT_SYSTEM.replace("{models}", ", ".join(KNOWN_MODELS))
    try:
        raw = await provider.chat(system, [ChatMessage("user", prompt)], json_mode=True, temperature=0.0)
        data = _parse_json(raw)
        if not data or "intent" not in data:
            raise ValueError("empty plan")
        plan = QueryPlan.model_validate({**data, "source": "llm"})
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        logger.info("query plan fallback to heuristics: %s", exc.__class__.__name__)
        plan = heuristic_plan(message, history)
    except Exception:  # noqa: BLE001 - LLM outage must not break chat
        logger.warning("query planning LLM call failed; using heuristics", exc_info=True)
        plan = heuristic_plan(message, history)
    return finalise_plan(plan, message, history)
