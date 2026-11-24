"""Hybrid retrieval: pgvector cosine + Postgres FTS, fused with RRF, balanced per vehicle."""

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.llm.base import LLMProvider
from app.models import Document
from app.rag.intent import QueryPlan

logger = logging.getLogger("app.rag")

CANDIDATES = 20
RRF_K = 60
MAX_CONTEXT_TOKENS = 12_000
VARIANT_BOOST = 0.01
SECTION_BOOST = 0.006
TABLE_BOOST = 0.004

ASPECT_SECTIONS: dict[str, set[str]] = {
    "engine": {"Engine & Performance", "Specifications"},
    "performance": {"Engine & Performance", "Specifications"},
    "fuel_efficiency": {"Engine & Performance", "Specifications"},
    "safety": {"Safety"},
    "comfort": {"Comfort & Convenience", "Interior"},
    "technology": {"Technology & Infotainment"},
    "dimensions": {"Dimensions", "Specifications"},
    "exterior": {"Exterior"},
    "interior": {"Interior"},
    "colours": {"Colours"},
    "variants": {"Variants & Features"},
    "price": {"Variants & Features", "Other"},
}


@dataclass
class RetrievedChunk:
    id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    vehicle_model: str
    page_number: int
    section: str | None
    variants: list[str]
    content_type: str
    content: str
    token_count: int
    score: float = 0.0


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    missing_vehicles: list[str] = field(default_factory=list)
    available_vehicles: list[str] = field(default_factory=list)


_VEC_SQL = text(
    """
    SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.status = 'ready' AND (CAST(:model AS text) IS NULL OR c.vehicle_model = :model)
    ORDER BY c.embedding <=> CAST(:qvec AS vector) LIMIT :lim
    """
)
_FTS_SQL = text(
    """
    SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.status = 'ready' AND (CAST(:model AS text) IS NULL OR c.vehicle_model = :model)
      AND c.tsv @@ websearch_to_tsquery('english', :q)
    ORDER BY ts_rank_cd(c.tsv, websearch_to_tsquery('english', :q)) DESC LIMIT :lim
    """
)
_TABLE_SQL = text(
    """
    SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.status = 'ready' AND c.vehicle_model = :model AND c.content_type IN ('table', 'ocr')
      AND c.section IN ('Specifications', 'Engine & Performance', 'Dimensions')
    ORDER BY c.embedding <=> CAST(:qvec AS vector) LIMIT :lim
    """
)
_FETCH_SQL = text(
    """
    SELECT c.id, c.document_id, d.display_name, c.vehicle_model, c.page_number, c.section, c.variants,
           c.content_type, c.content, c.token_count
    FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = ANY(:ids)
    """
)

_STOP = {
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "for",
    "in",
    "on",
    "to",
    "is",
    "are",
    "what",
    "which",
    "with",
    "vs",
    "hyundai",
    "does",
    "do",
    "have",
    "has",
    "how",
    "me",
    "all",
    "list",
    "compare",
    "tell",
    "about",
    "i",
    "my",
}


def or_query(q: str) -> str:
    """websearch_to_tsquery input that ORs the meaningful words (AND would be far too strict)."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", q) if w.lower() not in _STOP and len(w) > 1]
    return " or ".join(dict.fromkeys(words))[:500]


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


async def ready_vehicles(db: AsyncSession) -> list[str]:
    rows = await db.scalars(select(Document.vehicle_model).where(Document.status == "ready").distinct())
    return sorted(rows)


async def _hybrid(db: AsyncSession, model: str | None, query: str, qvec: list[float]) -> dict[uuid.UUID, float]:
    scores: dict[uuid.UUID, float] = {}
    vec_ids = (await db.execute(_VEC_SQL, {"model": model, "qvec": _vec_literal(qvec), "lim": CANDIDATES})).scalars()
    for rank, cid in enumerate(vec_ids, start=1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    tsq = or_query(query)
    if tsq:
        fts_ids = (await db.execute(_FTS_SQL, {"model": model, "q": tsq, "lim": CANDIDATES})).scalars()
        for rank, cid in enumerate(fts_ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def _queries_for(vehicle: str | None, plan: QueryPlan, all_vehicles: list[str]) -> list[str]:
    if vehicle is None:
        return plan.sub_queries
    own = [q for q in plan.sub_queries if vehicle.lower() in q.lower()]
    others = [v.lower() for v in all_vehicles if v != vehicle]
    generic = [q for q in plan.sub_queries if not any(o in q.lower() for o in others) and q not in own]
    return list(dict.fromkeys(own + [f"{vehicle} {q}" if vehicle.lower() not in q.lower() else q for q in generic]))


def per_vehicle_k(plan: QueryPlan, n_vehicles: int, top_k: int) -> int:
    if n_vehicles >= 3:
        return 5
    if n_vehicles == 2:
        return 6
    if plan.intent in ("feature_list", "variant_comparison"):
        return max(top_k, 12)
    return top_k


async def retrieve(db: AsyncSession, provider: LLMProvider, plan: QueryPlan) -> RetrievalResult:
    settings = get_settings()
    available = await ready_vehicles(db)
    result = RetrievalResult(available_vehicles=available)
    if not available:
        result.missing_vehicles = list(plan.vehicles)
        return result

    requested = plan.vehicles
    result.missing_vehicles = [v for v in requested if v not in available]
    targets: list[str | None] = [v for v in requested if v in available]
    if requested and not targets:
        return result
    if not targets:
        targets = [None]

    # embed every distinct query once
    per_target_queries = {t: _queries_for(t, plan, requested)[:8] for t in targets}
    distinct = list(dict.fromkeys(q for qs in per_target_queries.values() for q in qs))
    vectors = dict(zip(distinct, await provider.embed_queries(distinct), strict=True))

    k = per_vehicle_k(plan, len(targets), settings.RETRIEVAL_TOP_K)
    wanted_sections = set().union(*(ASPECT_SECTIONS.get(a, set()) for a in plan.aspects)) if plan.aspects else set()
    selected: dict[uuid.UUID, float] = {}
    forced: set[uuid.UUID] = set()

    for target in targets:
        fused: dict[uuid.UUID, float] = {}
        for q in per_target_queries[target]:
            for cid, s in (await _hybrid(db, target, q, vectors[q])).items():
                fused[cid] = fused.get(cid, 0.0) + s
        if not fused:
            continue
        meta = {r.id: r for r in await _fetch(db, list(fused))}
        wanted_variants = {v.lower() for v in plan.variants.get(target or "", [])}
        for cid, chunk in meta.items():
            if wanted_variants and {v.lower() for v in chunk.variants} & wanted_variants:
                fused[cid] += VARIANT_BOOST
            if chunk.section in wanted_sections:
                fused[cid] += SECTION_BOOST
            if chunk.content_type == "table" and plan.intent != "general":
                fused[cid] += TABLE_BOOST
        top = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        selected.update(top)

        if target and plan.intent in (
            "model_comparison",
            "variant_comparison",
            "spec_lookup",
            "recommendation",
            "feature_list",
        ):
            spec_q = per_target_queries[target][0]
            rows = await db.execute(_TABLE_SQL, {"model": target, "qvec": _vec_literal(vectors[spec_q]), "lim": 3})
            for cid in rows.scalars():
                if cid not in selected:
                    selected[cid] = fused.get(cid, 0.0)
                    forced.add(cid)

    chunks = await _fetch(db, list(selected))
    for c in chunks:
        c.score = selected[c.id]
    # token cap: drop lowest scored first (forced spec tables are kept as long as possible)
    chunks.sort(key=lambda c: (c.id in forced, c.score), reverse=True)
    kept: list[RetrievedChunk] = []
    used = 0
    for c in chunks:
        if used + c.token_count > MAX_CONTEXT_TOKENS:
            continue
        kept.append(c)
        used += c.token_count
    order = {v: i for i, v in enumerate(requested)}
    kept.sort(key=lambda c: (order.get(c.vehicle_model, 99), c.vehicle_model, c.section or "", c.page_number))
    result.chunks = kept
    logger.info("retrieved %s chunks (%s tokens) for %s; missing=%s", len(kept), used, targets, result.missing_vehicles)
    return result


async def _fetch(db: AsyncSession, ids: list[uuid.UUID]) -> list[RetrievedChunk]:
    if not ids:
        return []
    rows = (await db.execute(_FETCH_SQL, {"ids": ids})).all()
    return [
        RetrievedChunk(
            id=r.id,
            document_id=r.document_id,
            document_name=r.display_name,
            vehicle_model=r.vehicle_model,
            page_number=r.page_number,
            section=r.section,
            variants=list(r.variants or []),
            content_type=r.content_type,
            content=r.content,
            token_count=r.token_count,
        )
        for r in rows
    ]
