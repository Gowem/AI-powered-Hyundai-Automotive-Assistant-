from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import Chunk
from tests.conftest import register, upload_pdf
from tests.fixtures.make_pdf import default_rows, make_brochure


async def _chunk_count(doc_id: str) -> int:
    async with SessionLocal() as s:
        return await s.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id == doc_id)) or 0


async def test_upload_process_list_and_view(client: AsyncClient) -> None:
    await register(client)
    data = make_brochure("Alcazar", default_rows("Alcazar"), ["Fictional Alcazar paragraph."])
    res = await upload_pdf(client, data, "Alcazar-Brochure-2025.pdf")
    assert res["status_code"] == 200, res["json"]
    assert res["json"]["vehicle_model"] == "Alcazar"  # detected from filename
    doc = (await client.get(f"/api/documents/{res['document_id']}")).json()
    assert doc["status"] == "ready", doc
    assert doc["page_count"] == 2 and doc["chunk_count"] > 0 and doc["model_year"] == "2025"
    assert await _chunk_count(res["document_id"]) == doc["chunk_count"]

    listing = (await client.get("/api/documents")).json()
    assert listing["total"] == 1 and listing["ready_count"] == 1 and listing["items"][0]["owner_is_me"]
    assert (await client.get("/api/documents?vehicle_model=Creta")).json()["total"] == 0
    assert (await client.get("/api/documents?q=alcazar")).json()["total"] == 1

    url = (await client.get(f"/api/documents/{res['document_id']}/view-url")).json()["url"]
    pdf = await client.get(url)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")


async def test_validation_on_upload_url(client: AsyncClient) -> None:
    await register(client)
    r = await client.post("/api/documents/upload-url", json={"filename": "notes.txt", "file_size_bytes": 10})
    assert r.status_code == 422
    r = await client.post("/api/documents/upload-url", json={"filename": "a.pdf", "file_size_bytes": 999 * 1024**2})
    assert r.status_code == 422
    r = await client.post(
        "/api/documents/upload-url", json={"filename": "a.pdf", "file_size_bytes": 10, "vehicle_model": "Mustang"}
    )
    assert r.status_code == 422


async def test_non_pdf_bytes_rejected(client: AsyncClient) -> None:
    await register(client)
    res = await upload_pdf(client, b"this is not a pdf at all", "fake.pdf")
    assert res["status_code"] == 400
    assert (await client.get("/api/documents")).json()["total"] == 0


async def test_duplicate_sha256_rejected(client: AsyncClient) -> None:
    await register(client)
    data = make_brochure("Creta", default_rows("Creta"), ["Fictional Creta paragraph."])
    assert (await upload_pdf(client, data, "creta.pdf"))["status_code"] == 200
    dup = await upload_pdf(client, data, "creta-copy.pdf")
    assert dup["status_code"] == 409
    assert dup["json"]["detail"] == "This brochure is already uploaded"
    assert (await client.get("/api/documents")).json()["total"] == 1


async def test_only_owner_can_modify_and_delete_cascades(client: AsyncClient) -> None:
    await register(client, "owner@example.com")
    data = make_brochure("Venue", default_rows("Venue"), ["Fictional Venue paragraph."])
    doc_id = (await upload_pdf(client, data, "venue.pdf"))["document_id"]
    assert await _chunk_count(doc_id) > 0

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await register(other, "other@example.com")
        listing = (await other.get("/api/documents")).json()
        assert listing["total"] == 1 and listing["items"][0]["owner_is_me"] is False  # shared knowledge base
        assert (await other.delete(f"/api/documents/{doc_id}")).status_code == 403
        assert (await other.post(f"/api/documents/{doc_id}/reprocess")).status_code == 403
        assert (await other.patch(f"/api/documents/{doc_id}", json={"display_name": "x"})).status_code == 403

    r = await client.patch(f"/api/documents/{doc_id}", json={"display_name": "Venue 2025", "vehicle_model": "Exter"})
    assert r.status_code == 200 and r.json()["vehicle_model"] == "Exter"
    async with SessionLocal() as s:
        models = set(await s.scalars(select(Chunk.vehicle_model).where(Chunk.document_id == doc_id)))
    assert models == {"Exter"}

    r = await client.post(f"/api/documents/{doc_id}/reprocess")
    assert r.status_code == 200
    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "ready"

    assert (await client.delete(f"/api/documents/{doc_id}")).status_code == 204
    assert await _chunk_count(doc_id) == 0
    assert (await client.get(f"/api/documents/{doc_id}")).status_code == 404
