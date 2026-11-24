"""End-to-end answer generation: plan -> retrieve -> grounded (streamed) generation -> citations."""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import ChatMessage, LLMProvider
from app.rag.citations import build_sources, format_context, strip_invalid_citations
from app.rag.intent import QueryPlan, plan_query
from app.rag.prompts import (
    NO_CONTEXT_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    SYSTEM_PROMPT,
    TEMPLATES,
    missing_vehicle_notice,
)
from app.rag.retriever import RetrievalResult, retrieve
from app.schemas import SourceOut

logger = logging.getLogger("app.rag")

HISTORY_MESSAGES = 6


@dataclass
class AgentEvent:
    kind: Literal["status", "token"]
    data: dict[str, Any]


@dataclass
class AgentAnswer:
    content: str
    sources: list[SourceOut] = field(default_factory=list)
    intent: str | None = None
    plan: QueryPlan | None = None


def build_system_prompt(plan: QueryPlan, retrieval: RetrievalResult) -> str:
    template = TEMPLATES.get(plan.intent, TEMPLATES["general"])
    req = plan.requirements.model_dump(exclude_none=True)
    lines = [
        SYSTEM_PROMPT,
        template,
        f"QUESTION TYPE: {plan.intent}",
        f"VEHICLES REQUESTED: {plan.vehicles or 'not specified'}",
    ]
    if plan.variants:
        lines.append(f"VARIANTS REQUESTED: {plan.variants}")
    if plan.aspects:
        lines.append(f"ASPECTS TO COVER: {plan.aspects}")
    if req and plan.intent == "recommendation":
        lines.append(f"CUSTOMER REQUIREMENTS: {req}")
    lines.append(f"MISSING_VEHICLES: {retrieval.missing_vehicles}")
    if retrieval.missing_vehicles:
        lines.append(
            'For each missing vehicle write exactly: "'
            + missing_vehicle_notice(retrieval.missing_vehicles)
            + '" and do not describe it from memory.'
        )
    lines.append(f"BROCHURES AVAILABLE FOR: {retrieval.available_vehicles}")
    lines.append("SOURCES:\n" + format_context(retrieval.chunks))
    return "\n\n".join(lines)


async def run_agent(
    db: AsyncSession, provider: LLMProvider, message: str, history: list[ChatMessage]
) -> AsyncIterator[AgentEvent | AgentAnswer]:
    history = history[-HISTORY_MESSAGES:]
    yield AgentEvent("status", {"stage": "understanding"})
    plan = await plan_query(provider, message, history)
    logger.info("plan intent=%s vehicles=%s source=%s", plan.intent, plan.vehicles, plan.source)

    if plan.intent == "out_of_scope":
        yield AgentAnswer(OUT_OF_SCOPE_MESSAGE, [], plan.intent, plan)
        return

    yield AgentEvent("status", {"stage": "retrieving"})
    retrieval = await retrieve(db, provider, plan)

    if not retrieval.chunks:
        if retrieval.missing_vehicles:
            text = missing_vehicle_notice(retrieval.missing_vehicles)
            if not retrieval.available_vehicles:
                text = "No brochures have been indexed yet. Upload brochures on the Documents page to start."
            elif set(retrieval.missing_vehicles) == set(plan.vehicles):
                text += f"\n\nBrochures are currently available for: {', '.join(retrieval.available_vehicles)}."
            yield AgentAnswer(text, [], plan.intent, plan)
        else:
            yield AgentAnswer(NO_CONTEXT_MESSAGE, [], plan.intent, plan)
        return

    yield AgentEvent("status", {"stage": "writing"})
    system = build_system_prompt(plan, retrieval)
    messages = [*history, ChatMessage("user", message)]
    parts: list[str] = []
    async for token in provider.chat_stream(system, messages):
        parts.append(token)
        yield AgentEvent("token", {"text": token})
    answer = "".join(parts).strip()
    if not answer:
        answer = NO_CONTEXT_MESSAGE
    answer = strip_invalid_citations(answer, len(retrieval.chunks))
    sources = build_sources(answer, retrieval.chunks)
    yield AgentAnswer(answer, sources, plan.intent, plan)
