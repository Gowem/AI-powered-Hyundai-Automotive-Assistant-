import os
import tempfile

os.environ.update(
    APP_ENV="test",
    DATABASE_URL=os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/hyundai_test"
    ),
    LLM_PROVIDER="fake",
    STORAGE_BACKEND="local",
    LOCAL_UPLOAD_DIR=tempfile.mkdtemp(prefix="hyundai-test-uploads-"),
    JWT_SECRET="test-secret-test-secret-test-secret-test-secret-123456",
    VISION_OCR_FALLBACK="false",
)

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.llm import set_provider  # noqa: E402
from app.llm.fake import FakeProvider  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users, documents, chunks, conversations, messages CASCADE"))
    yield


@pytest.fixture
def fake_llm() -> FakeProvider:
    p = FakeProvider(768)
    set_provider(p)
    return p


@pytest.fixture
async def client(fake_llm: FakeProvider) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def register(c: AsyncClient, email: str = "user@example.com", password: str = "Passw0rd!") -> dict:
    r = await c.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


async def upload_pdf(
    c: AsyncClient, data: bytes, filename: str = "alcazar-brochure.pdf", vehicle_model: str | None = None
) -> dict:
    r = await c.post(
        "/api/documents/upload-url",
        json={"filename": filename, "file_size_bytes": len(data), "vehicle_model": vehicle_model},
    )
    assert r.status_code == 200, r.text
    info = r.json()
    r = await c.put(f"{info['upload_url']}?token={info['token']}", content=data)
    assert r.status_code == 204, r.text
    r = await c.post(f"/api/documents/{info['document_id']}/confirm")
    return {"status_code": r.status_code, "json": r.json(), "document_id": info["document_id"]}
