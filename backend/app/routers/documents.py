"""Brochure management: upload (signed URL or local), confirm, list, view, rename, reprocess, delete."""

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.ingestion import pipeline
from app.models import Chunk, Document, User
from app.schemas import (
    DocumentList,
    DocumentOut,
    DocumentPatch,
    UploadUrlIn,
    UploadUrlOut,
    VehicleList,
    ViewUrlOut,
)
from app.security import get_current_user
from app.storage import VIEW_URL_TTL, LocalStorage, StorageError, get_storage
from app.vehicles import KNOWN_MODELS, OTHER, detect_from_filename, normalise_vehicle

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger("app.documents")
settings = get_settings()


def to_out(doc: Document, user: User) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        display_name=doc.display_name,
        original_filename=doc.original_filename,
        vehicle_model=doc.vehicle_model,
        model_year=doc.model_year,
        uploaded_at=doc.uploaded_at,
        processed_at=doc.processed_at,
        status=doc.status,  # type: ignore[arg-type]
        status_detail=doc.status_detail,
        page_count=doc.page_count,
        chunk_count=doc.chunk_count,
        file_size_bytes=doc.file_size_bytes,
        owner_is_me=doc.owner_id == user.id,
    )


def resolve_model(value: str | None, filename: str | None = None) -> str:
    """Canonical model, 'Other: <text>' style free text, or Unknown (detected later)."""
    if value and value.strip():
        v = value.strip()
        canon = normalise_vehicle(v)
        if canon:
            return canon
        if v.lower() == OTHER.lower():
            return OTHER
        if v.lower().startswith("other:"):
            free = v.split(":", 1)[1].strip()
            return free[:60] if free else OTHER
        raise HTTPException(status_code=422, detail=f"Unknown vehicle model '{v}'. Choose from the list or 'Other'.")
    if filename:
        return detect_from_filename(filename) or pipeline.UNKNOWN_MODEL
    return pipeline.UNKNOWN_MODEL


async def _get_visible(db: AsyncSession, doc_id: uuid.UUID, user: User) -> Document:
    doc = await db.get(Document, doc_id)
    if doc is None or (doc.status == "pending_upload" and doc.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


async def _get_owned(db: AsyncSession, doc_id: uuid.UUID, user: User) -> Document:
    doc = await _get_visible(db, doc_id, user)
    if doc.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the uploader can modify this document")
    return doc


@router.get("/vehicles", response_model=VehicleList)
async def vehicles(_: User = Depends(get_current_user)) -> VehicleList:
    return VehicleList(models=[*KNOWN_MODELS, OTHER])


@router.post("/upload-url", response_model=UploadUrlOut)
async def create_upload_url(
    body: UploadUrlIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> UploadUrlOut:
    model = resolve_model(body.vehicle_model, body.filename)
    doc_id = uuid.uuid4()
    key = f"{doc_id}.pdf"
    display = (body.display_name or "").strip() or body.filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
    doc = Document(
        id=doc_id,
        owner_id=user.id,
        original_filename=body.filename,
        display_name=display[:200],
        vehicle_model=model,
        storage_path=key,
        file_size_bytes=body.file_size_bytes,
        status="pending_upload",
    )
    db.add(doc)
    await db.commit()
    storage = get_storage()
    try:
        signed = await storage.create_signed_upload(key, doc_id)
    except StorageError as exc:
        await db.delete(doc)
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return UploadUrlOut(
        document_id=doc_id,
        path=signed.path,
        token=signed.token,
        mode=storage.mode,  # type: ignore[arg-type]
        upload_url=signed.upload_url,
    )


@router.put("/{doc_id}/upload", status_code=204)
async def local_upload(
    doc_id: uuid.UUID,
    request: Request,
    token: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Upload target for STORAGE_BACKEND=local (replaces the Supabase signed upload)."""
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status_code=404, detail="Not available with this storage backend")
    doc = await _get_owned(db, doc_id, user)
    if doc.status != "pending_upload" or not storage.verify_token(token, doc_id, "upload"):
        raise HTTPException(status_code=403, detail="Invalid upload token")
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    dest = storage.path_for(doc.storage_path)
    tmp = dest.with_suffix(".part")
    size = 0
    try:
        with open(tmp, "wb") as f:  # noqa: ASYNC230 - small sequential writes of streamed chunks
            async for block in request.stream():
                size += len(block)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit")
                f.write(block)
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink()


async def _discard(db: AsyncSession, doc: Document) -> None:
    try:
        await get_storage().delete(doc.storage_path)
    except StorageError:
        logger.warning("could not delete storage object for %s", doc.id)
    await db.delete(doc)
    await db.commit()


@router.post("/{doc_id}/confirm", response_model=DocumentOut)
async def confirm_upload(
    doc_id: uuid.UUID,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    doc = await _get_owned(db, doc_id, user)
    if doc.status != "pending_upload":
        raise HTTPException(status_code=409, detail="This upload was already confirmed")
    try:
        file = await get_storage().download_to_temp(doc.storage_path)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail="The file has not been uploaded yet") from exc
    try:
        if not file.head.startswith(b"%PDF-"):
            await _discard(db, doc)
            raise HTTPException(status_code=400, detail="This file is not a valid PDF")
        if file.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            await _discard(db, doc)
            raise HTTPException(status_code=413, detail=f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit")
        dup = await db.scalar(
            select(Document.id).where(
                Document.owner_id == user.id, Document.sha256 == file.sha256, Document.id != doc.id
            )
        )
        if dup is not None:
            await _discard(db, doc)
            raise HTTPException(status_code=409, detail="This brochure is already uploaded")
        doc.sha256 = file.sha256
        doc.file_size_bytes = file.size
        doc.status = "queued"
        doc.status_detail = "Waiting to be processed"
        await db.commit()
        await db.refresh(doc)
    finally:
        file.cleanup()
    background.add_task(pipeline.process_document, doc.id)
    return to_out(doc, user)


def _filtered(
    stmt: Select[tuple[Document]], q: str | None, vehicle_model: str | None, status: str | None
) -> Select[tuple[Document]]:
    stmt = stmt.where(Document.status != "pending_upload")
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Document.display_name.ilike(like), Document.original_filename.ilike(like)))
    if vehicle_model:
        stmt = stmt.where(Document.vehicle_model == vehicle_model)
    if status:
        stmt = stmt.where(Document.status == status)
    return stmt


@router.get("", response_model=DocumentList)
async def list_documents(
    q: str | None = Query(default=None, max_length=200),
    vehicle_model: str | None = None,
    status: Literal["queued", "processing", "ready", "failed"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentList:
    base = _filtered(select(Document), q, vehicle_model, status)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = await db.scalars(base.order_by(Document.uploaded_at.desc()).limit(limit).offset(offset))
    ready = await db.scalar(select(func.count()).where(Document.status == "ready")) or 0
    return DocumentList(items=[to_out(d, user) for d in rows], total=total, ready_count=ready)


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(
    doc_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> DocumentOut:
    return to_out(await _get_visible(db, doc_id, user), user)


@router.get("/{doc_id}/view-url", response_model=ViewUrlOut)
async def view_url(
    doc_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ViewUrlOut:
    doc = await _get_visible(db, doc_id, user)
    try:
        url = await get_storage().signed_view_url(doc.storage_path, doc.id)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ViewUrlOut(url=url, expires_in=VIEW_URL_TTL)


@router.get("/{doc_id}/file")
async def local_file(
    doc_id: uuid.UUID,
    token: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    storage = get_storage()
    if not isinstance(storage, LocalStorage) or not storage.verify_token(token, doc_id, "view"):
        raise HTTPException(status_code=403, detail="Invalid or expired link")
    doc = await _get_visible(db, doc_id, user)
    path = storage.path_for(doc.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.original_filename}"'},
    )


@router.patch("/{doc_id}", response_model=DocumentOut)
async def patch_document(
    doc_id: uuid.UUID, body: DocumentPatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> DocumentOut:
    doc = await _get_owned(db, doc_id, user)
    if body.display_name is not None:
        doc.display_name = body.display_name.strip()
    if body.vehicle_model is not None:
        model = resolve_model(body.vehicle_model)
        if model != doc.vehicle_model:
            doc.vehicle_model = model
            await db.execute(update(Chunk).where(Chunk.document_id == doc.id).values(vehicle_model=model))
    await db.commit()
    await db.refresh(doc)
    return to_out(doc, user)


@router.post("/{doc_id}/reprocess", response_model=DocumentOut)
async def reprocess(
    doc_id: uuid.UUID,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    doc = await _get_owned(db, doc_id, user)
    if doc.status == "pending_upload":
        raise HTTPException(status_code=409, detail="Upload has not been confirmed")
    if doc.status in ("queued", "processing"):
        raise HTTPException(status_code=409, detail="This document is already being processed")
    await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    doc.status, doc.status_detail, doc.chunk_count = "queued", "Waiting to be processed", 0
    await db.commit()
    await db.refresh(doc)
    background.add_task(pipeline.process_document, doc.id)
    return to_out(doc, user)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    doc = await _get_owned(db, doc_id, user)
    try:
        await get_storage().delete(doc.storage_path)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await db.delete(doc)
    await db.commit()
