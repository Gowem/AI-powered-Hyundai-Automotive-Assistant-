"""Document processing pipeline: download -> parse -> clean -> chunk -> embed -> insert."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text, update

from app.config import get_settings
from app.db import SessionLocal
from app.ingestion.chunker import chunk_pages
from app.ingestion.metadata import detect_model_year, detect_vehicle
from app.ingestion.pdf_parser import PageContent, clean_pages, parse_pdf, render_page_png
from app.llm import get_provider
from app.models import Chunk, Document
from app.storage import get_storage

logger = logging.getLogger("app.ingestion")

OCR_PROMPT = (
    "Transcribe all text on this brochure page exactly. Render tables as Markdown tables. "
    "Do not add anything that is not on the page."
)
OCR_MAX_PAGES = 40
OCR_CONCURRENCY = 3
EMBED_BATCH = 50
UNKNOWN_MODEL = "Unknown"

_running: set[uuid.UUID] = set()
# One document at a time keeps peak memory low on small (512 MB) instances.
_process_lock = asyncio.Semaphore(1)
_tasks: set[asyncio.Task[None]] = set()


class PipelineError(Exception):
    """An error with a short, user-readable message."""


async def _set_status(doc_id: uuid.UUID, status: str | None = None, detail: str | None = None, **extra: object) -> None:
    values: dict[str, object] = {"status_detail": detail, **extra}
    if status:
        values["status"] = status
    async with SessionLocal() as s:
        await s.execute(update(Document).where(Document.id == doc_id).values(**values))
        await s.commit()


async def _ocr_pages(path: str, pages: list[PageContent], doc_id: uuid.UUID) -> None:
    targets = [p for p in pages if p.needs_ocr][:OCR_MAX_PAGES]
    if not targets:
        return
    provider = get_provider()
    sem = asyncio.Semaphore(OCR_CONCURRENCY)
    done = 0

    async def one(p: PageContent) -> None:
        nonlocal done
        async with sem:
            try:
                png = await asyncio.to_thread(render_page_png, path, p.page_number)
                text = (await provider.transcribe_image(png, OCR_PROMPT)).strip()
                if len(text) >= 20:
                    p.ocr_text = text
            except Exception:  # noqa: BLE001 - OCR is best effort
                logger.warning("OCR failed for page %s of %s", p.page_number, doc_id, exc_info=True)
            done += 1
            await _set_status(doc_id, detail=f"OCR {done}/{len(targets)} image-only pages")

    await asyncio.gather(*(one(p) for p in targets))


def _short_error(exc: BaseException) -> str:
    if isinstance(exc, PipelineError):
        return str(exc)
    msg = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return f"Processing failed: {msg[:200]}"


async def process_document(doc_id: uuid.UUID) -> None:
    if doc_id in _running:
        logger.info("document %s already processing", doc_id)
        return
    _running.add(doc_id)
    try:
        async with _process_lock:
            await _process(doc_id)
    finally:
        _running.discard(doc_id)


async def _process(doc_id: uuid.UUID) -> None:
    settings = get_settings()
    downloaded = None
    try:
        async with SessionLocal() as s:
            doc = await s.get(Document, doc_id)
            if doc is None:
                return
            storage_key, filename, display_name = doc.storage_path, doc.original_filename, doc.display_name
            vehicle = doc.vehicle_model
        await _set_status(doc_id, "processing", "Downloading")
        downloaded = await get_storage().download_to_temp(storage_key)

        await _set_status(doc_id, detail="Parsing PDF")
        try:
            pages = await asyncio.to_thread(parse_pdf, downloaded.local_path)
        except Exception as exc:
            raise PipelineError("Could not read this PDF (it may be corrupted or encrypted)") from exc
        if not pages:
            raise PipelineError("The PDF has no pages")
        pages = await asyncio.to_thread(clean_pages, pages)

        if settings.VISION_OCR_FALLBACK and any(p.needs_ocr for p in pages):
            await _ocr_pages(downloaded.local_path, pages, doc_id)

        first_texts = [(p.ocr_text or p.text) + "\n" + "\n".join(p.tables) for p in pages[:2]]
        if vehicle in ("", UNKNOWN_MODEL):
            vehicle = detect_vehicle(first_texts) or detect_vehicle([p.text for p in pages]) or "Other"
        model_year = detect_model_year(filename, first_texts)

        await _set_status(doc_id, detail="Chunking")
        chunks = chunk_pages(pages, vehicle, display_name)
        if not chunks:
            raise PipelineError("No extractable text found in this PDF")

        provider = get_provider()
        vectors: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH):
            await _set_status(doc_id, detail=f"Embedding {i}/{len(chunks)}")
            batch = chunks[i : i + EMBED_BATCH]
            vectors.extend(await provider.embed([c.content for c in batch]))
        await _set_status(doc_id, detail=f"Embedding {len(chunks)}/{len(chunks)}")

        await _set_status(doc_id, detail="Saving")
        async with SessionLocal() as s, s.begin():
            await s.execute(delete(Chunk).where(Chunk.document_id == doc_id))
            s.add_all(
                Chunk(
                    document_id=doc_id,
                    vehicle_model=vehicle,
                    page_number=c.page_number,
                    chunk_index=c.chunk_index,
                    section=c.section,
                    variants=c.variants or None,
                    content_type=c.content_type,
                    content=c.content,
                    token_count=c.token_count,
                    embedding=v,
                )
                for c, v in zip(chunks, vectors, strict=True)
            )
            await s.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    status="ready",
                    status_detail=None,
                    vehicle_model=vehicle,
                    model_year=model_year,
                    page_count=len(pages),
                    chunk_count=len(chunks),
                    processed_at=datetime.now(UTC),
                )
            )
        logger.info("document %s ready: %s pages, %s chunks", doc_id, len(pages), len(chunks))
    except Exception as exc:
        logger.exception("processing failed for document %s", doc_id)
        try:
            await _set_status(doc_id, "failed", _short_error(exc))
        except Exception:  # noqa: BLE001
            logger.exception("could not mark document %s failed", doc_id)
    finally:
        if downloaded:
            downloaded.cleanup()


def schedule(doc_id: uuid.UUID) -> None:
    """Fire-and-forget scheduling that keeps a reference to the task."""
    task = asyncio.create_task(process_document(doc_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def recover_stuck_documents() -> int:
    """Re-queue documents interrupted by a restart; drop uploads never confirmed within a day."""
    async with SessionLocal() as s:
        stale = list(
            await s.scalars(
                select(Document).where(
                    Document.status == "pending_upload", Document.uploaded_at < func.now() - text("interval '1 day'")
                )
            )
        )
        for doc in stale:
            try:
                await get_storage().delete(doc.storage_path)
            except Exception:  # noqa: BLE001
                logger.warning("could not delete stale upload %s", doc.id)
            await s.delete(doc)
        await s.commit()
    async with SessionLocal() as s:
        ids = list(await s.scalars(select(Document.id).where(Document.status.in_(("queued", "processing")))))
    for doc_id in ids:
        await _set_status(doc_id, "queued", "Re-queued after restart")
        schedule(doc_id)
    if ids:
        logger.info("re-queued %s stuck documents", len(ids))
    return len(ids)
