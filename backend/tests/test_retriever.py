import uuid

from app.db import SessionLocal
from app.llm.fake import FakeProvider, hashed_embedding
from app.models import Chunk, Document, User
from app.rag.intent import QueryPlan, finalise_plan
from app.rag.retriever import or_query, retrieve


async def _seed(vehicle: str, n: int, owner: uuid.UUID, text_word: str) -> None:
    async with SessionLocal() as s:
        doc = Document(
            owner_id=owner,
            original_filename=f"{vehicle}.pdf",
            display_name=f"{vehicle} Brochure",
            vehicle_model=vehicle,
            storage_path=f"{uuid.uuid4()}.pdf",
            status="ready",
            file_size_bytes=1,
        )
        s.add(doc)
        await s.flush()
        for i in range(n):
            content = f"[Vehicle: {vehicle}] {vehicle} engine power torque {text_word} fact {i}"
            s.add(
                Chunk(
                    document_id=doc.id,
                    vehicle_model=vehicle,
                    page_number=i + 1,
                    chunk_index=i,
                    section="Engine & Performance",
                    content_type="table" if i == 0 else "text",
                    content=content,
                    token_count=20,
                    embedding=hashed_embedding(content, 768),
                )
            )
        await s.commit()


async def _owner() -> uuid.UUID:
    async with SessionLocal() as s:
        u = User(email=f"{uuid.uuid4()}@x.com", password_hash="x")
        s.add(u)
        await s.commit()
        return u.id


async def test_per_vehicle_balancing_returns_both_vehicles() -> None:
    owner = await _owner()
    # Alcazar has far more (and more query-like) chunks; Creta must still be represented.
    await _seed("Alcazar", 40, owner, "engine power torque engine power")
    await _seed("Creta", 5, owner, "misc")
    plan = finalise_plan(
        QueryPlan(intent="model_comparison", vehicles=["Alcazar", "Creta"]), "Compare Alcazar and Creta engines", []
    )
    async with SessionLocal() as db:
        result = await retrieve(db, FakeProvider(), plan)
    by_vehicle = {c.vehicle_model for c in result.chunks}
    assert by_vehicle == {"Alcazar", "Creta"}
    assert sum(c.vehicle_model == "Alcazar" for c in result.chunks) <= 6 + 3
    assert sum(c.vehicle_model == "Creta" for c in result.chunks) >= 3
    assert result.missing_vehicles == []
    # ordered by vehicle as requested
    first_creta = next(i for i, c in enumerate(result.chunks) if c.vehicle_model == "Creta")
    assert all(c.vehicle_model == "Alcazar" for c in result.chunks[:first_creta])


async def test_missing_vehicle_is_reported_not_retrieved() -> None:
    owner = await _owner()
    await _seed("Alcazar", 3, owner, "x")
    plan = finalise_plan(
        QueryPlan(intent="model_comparison", vehicles=["Alcazar", "Tucson"]), "Compare Alcazar with Tucson", []
    )
    async with SessionLocal() as db:
        result = await retrieve(db, FakeProvider(), plan)
    assert result.missing_vehicles == ["Tucson"]
    assert {c.vehicle_model for c in result.chunks} == {"Alcazar"}


def test_or_query() -> None:
    assert or_query("What is the boot space of the Creta?") == "boot or space or Creta"
