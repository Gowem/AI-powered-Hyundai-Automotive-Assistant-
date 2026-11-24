import uuid

from httpx import AsyncClient

from app.db import SessionLocal
from app.llm.base import ChatMessage
from app.llm.fake import FakeProvider, hashed_embedding
from app.models import Chunk, Document, User
from app.rag.agent import AgentAnswer, run_agent
from app.rag.citations import build_sources, cited_numbers, strip_invalid_citations
from app.rag.intent import heuristic_plan
from app.rag.prompts import NO_CONTEXT_MESSAGE, OUT_OF_SCOPE_MESSAGE
from app.rag.retriever import RetrievedChunk
from tests.conftest import register


class CountingProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__(768)
        self.stream_calls = 0

    def chat_stream(self, system, messages, *, temperature=0.2):  # type: ignore[no-untyped-def]
        self.stream_calls += 1
        return super().chat_stream(system, messages, temperature=temperature)


async def _answer(provider: FakeProvider, message: str, history: list[ChatMessage] | None = None) -> AgentAnswer:
    async with SessionLocal() as db:
        final = None
        async for ev in run_agent(db, provider, message, history or []):
            if isinstance(ev, AgentAnswer):
                final = ev
        assert final is not None
        return final


async def _seed_alcazar() -> None:
    async with SessionLocal() as s:
        u = User(email=f"{uuid.uuid4()}@x.com", password_hash="x")
        s.add(u)
        await s.flush()
        d = Document(
            owner_id=u.id,
            original_filename="a.pdf",
            display_name="Alcazar Brochure",
            vehicle_model="Alcazar",
            storage_path="a.pdf",
            status="ready",
            file_size_bytes=1,
        )
        s.add(d)
        await s.flush()
        content = "[Vehicle: Alcazar | Page 3 | Section: Safety]\nAlcazar fictional safety airbags fact"
        s.add(
            Chunk(
                document_id=d.id,
                vehicle_model="Alcazar",
                page_number=3,
                chunk_index=0,
                section="Safety",
                content_type="text",
                content=content,
                token_count=12,
                embedding=hashed_embedding(content, 768),
            )
        )
        await s.commit()


async def test_no_chunks_returns_fixed_message_without_generation() -> None:
    p = CountingProvider()
    async with SessionLocal() as s:  # one ready doc for some other model, so retrieval runs but finds nothing
        u = User(email="z@x.com", password_hash="x")
        s.add(u)
        await s.flush()
        s.add(
            Document(
                owner_id=u.id,
                original_filename="v.pdf",
                display_name="Venue",
                vehicle_model="Venue",
                storage_path="v.pdf",
                status="ready",
                file_size_bytes=1,
            )
        )
        await s.commit()
    ans = await _answer(p, "Tell me about the warranty terms for cars")
    assert ans.content == NO_CONTEXT_MESSAGE
    assert p.stream_calls == 0
    assert ans.sources == []


async def test_missing_vehicle_notice() -> None:
    await _seed_alcazar()
    p = CountingProvider()
    ans = await _answer(p, "Compare Alcazar with Tucson on safety")
    assert p.stream_calls == 1
    system = p.chat_calls[-1][0]
    assert "MISSING_VEHICLES: ['Tucson']" in system
    assert "No Tucson brochure has been uploaded yet" in system
    # only a missing vehicle -> fixed notice, no generation
    p2 = CountingProvider()
    ans = await _answer(p2, "What are the features of the Tucson?")
    assert "No Tucson brochure has been uploaded yet" in ans.content
    assert p2.stream_calls == 0


async def test_out_of_scope_skips_retrieval() -> None:
    p = CountingProvider()
    ans = await _answer(p, "Who won the cricket match?")
    assert ans.content == OUT_OF_SCOPE_MESSAGE and p.stream_calls == 0


async def test_follow_up_resolves_vehicle_from_history() -> None:
    plan = heuristic_plan(
        "What about its safety features?",
        [
            ChatMessage("user", "List all features of the Hyundai Alcazar"),
            ChatMessage("assistant", "## Alcazar: Key Features ..."),
        ],
    )
    assert plan.vehicles == ["Alcazar"]
    assert "safety" in plan.aspects


def test_heuristic_intents() -> None:
    assert heuristic_plan("Compare Alcazar vs Creta", []).intent == "model_comparison"
    assert heuristic_plan("Compare all Alcazar variants", []).intent == "variant_comparison"
    assert heuristic_plan("Compare Alcazar Prestige vs Platinum vs Signature", []).intent == "variant_comparison"
    assert heuristic_plan("I drive in the city, family of 4: i20 or Aura?", []).intent == "recommendation"
    assert heuristic_plan("List all features of the Hyundai Alcazar", []).intent == "feature_list"
    assert heuristic_plan("What is the boot space of the Creta?", []).intent == "spec_lookup"
    assert heuristic_plan("Who won the cricket match?", []).intent == "out_of_scope"
    assert heuristic_plan("hyundai alcazr features", []).vehicles == ["Alcazar"]


def _chunk(n: int) -> RetrievedChunk:
    return RetrievedChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name=f"Doc {n}",
        vehicle_model="Alcazar",
        page_number=n,
        section="Safety",
        variants=[],
        content_type="text",
        content=f"[Vehicle: Alcazar]\ncontent {n}",
        token_count=5,
    )


def test_citation_parsing() -> None:
    chunks = [_chunk(i) for i in range(1, 6)]
    answer = "Power 1 [2]. Torque [4][2]. Both [1, 3]. Bogus [9]."
    assert cited_numbers(answer) == [2, 4, 1, 3, 9]
    cleaned = strip_invalid_citations(answer, len(chunks))
    assert "[9]" not in cleaned and "[1][3]" in cleaned
    sources = build_sources(cleaned, chunks)
    assert [s.n for s in sources] == [1, 2, 3, 4]
    assert sources[1].page == 2 and sources[1].snippet == "content 2"
    # no citations -> top 3 attached
    assert [s.n for s in build_sources("no cites", chunks)] == [1, 2, 3]


async def test_chat_endpoint_non_stream_and_stream(client: AsyncClient) -> None:
    await register(client)
    await _seed_alcazar()
    conv = (await client.post("/api/chat/conversations")).json()
    r = await client.post(
        f"/api/chat/conversations/{conv['id']}/messages?stream=false",
        json={"content": "What safety features does the Alcazar have?"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sources"] and body["sources"][0]["page"] == 3
    assert body["conversation_title"].startswith("What safety features")

    async with client.stream(
        "POST", f"/api/chat/conversations/{conv['id']}/messages", json={"content": "And its airbags?"}
    ) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-cache, no-transform"
        raw = "".join([chunk async for chunk in resp.aiter_text()])
    for ev in ("event: status", "event: token", "event: sources", "event: done"):
        assert ev in raw
    detail = (await client.get(f"/api/chat/conversations/{conv['id']}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]

    r = await client.post(f"/api/chat/conversations/{conv['id']}/messages?stream=false", json={"content": "x" * 2001})
    assert r.status_code == 422
