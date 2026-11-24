"""Conversations and messages. Every query is scoped to the current user."""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, get_db
from app.llm import get_provider
from app.llm.base import ChatMessage
from app.models import Conversation, Message, User
from app.rag.agent import AgentAnswer, AgentEvent, run_agent
from app.schemas import (
    ChatAnswer,
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationOut,
    ConversationPatch,
    MessageIn,
    MessageOut,
    SourceOut,
)
from app.security import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("app.chat")


def conv_out(c: Conversation) -> ConversationOut:
    return ConversationOut(id=c.id, title=c.title, created_at=c.created_at, updated_at=c.updated_at)


def msg_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        intent=m.intent,
        created_at=m.created_at,  # type: ignore[arg-type]
        sources=[SourceOut.model_validate(s) for s in m.sources] if m.sources is not None else None,
    )


async def _owned(db: AsyncSession, conv_id: uuid.UUID, user: User) -> Conversation:
    conv = await db.scalar(select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user.id))
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def make_title(text: str) -> str:
    words = text.replace("\n", " ").split()
    title = " ".join(words[:6])
    if len(words) > 6:
        title += "…"
    return title[:80] or "New chat"


@router.get("/conversations", response_model=ConversationList)
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationList:
    base = select(Conversation).where(Conversation.user_id == user.id)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = await db.scalars(base.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset))
    return ConversationList(items=[conv_out(c) for c in rows], total=total)


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ConversationOut:
    conv = Conversation(user_id=user.id, title=(body.title if body and body.title else "New chat"))
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv_out(conv)


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ConversationDetail:
    conv = await _owned(db, conv_id, user)
    msgs = await db.scalars(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at, Message.role.desc())
    )
    return ConversationDetail(**conv_out(conv).model_dump(), messages=[msg_out(m) for m in msgs])


@router.patch("/conversations/{conv_id}", response_model=ConversationOut)
async def rename_conversation(
    conv_id: uuid.UUID,
    body: ConversationPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conv = await _owned(db, conv_id, user)
    conv.title = body.title.strip()
    await db.commit()
    await db.refresh(conv)
    return conv_out(conv)


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    conv = await _owned(db, conv_id, user)
    await db.delete(conv)
    await db.commit()


async def _prepare(db: AsyncSession, conv: Conversation, body: MessageIn) -> tuple[list[ChatMessage], Message]:
    """Load history and persist the user message (or reuse it when regenerating)."""
    rows = list(
        await db.scalars(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.desc()).limit(20)
        )
    )
    rows.reverse()
    if body.regenerate:
        # drop the trailing assistant answer and reuse the last user message
        if rows and rows[-1].role == "assistant":
            await db.execute(delete(Message).where(Message.id == rows[-1].id))
            rows = rows[:-1]
        if rows and rows[-1].role == "user" and rows[-1].content == body.content:
            user_msg = rows[-1]
            rows = rows[:-1]
            await db.commit()
            return [ChatMessage(m.role, m.content) for m in rows], user_msg  # type: ignore[arg-type]
    user_msg = Message(conversation_id=conv.id, role="user", content=body.content)
    db.add(user_msg)
    if conv.title == "New chat":
        conv.title = make_title(body.content)
    conv.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user_msg)
    return [ChatMessage(m.role, m.content) for m in rows], user_msg  # type: ignore[arg-type]


async def _save_answer(conv_id: uuid.UUID, answer: AgentAnswer) -> tuple[Message, str]:
    async with SessionLocal() as s:
        msg = Message(
            conversation_id=conv_id,
            role="assistant",
            content=answer.content,
            sources=[src.model_dump(mode="json") for src in answer.sources],
            intent=answer.intent,
        )
        s.add(msg)
        conv = await s.get(Conversation, conv_id)
        assert conv is not None
        conv.updated_at = datetime.now(UTC)
        await s.commit()
        await s.refresh(msg)
        return msg, conv.title


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/conversations/{conv_id}/messages", response_model=ChatAnswer)
async def send_message(
    conv_id: uuid.UUID,
    body: MessageIn,
    stream: bool = Query(default=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    conv = await _owned(db, conv_id, user)
    history, user_msg = await _prepare(db, conv, body)
    provider = get_provider()

    if not stream:
        final: AgentAnswer | None = None
        try:
            async for ev in run_agent(db, provider, body.content, history):
                if isinstance(ev, AgentAnswer):
                    final = ev
        except Exception as exc:
            logger.exception("chat generation failed")
            raise HTTPException(
                status_code=502, detail="The assistant could not generate an answer. Please retry."
            ) from exc
        assert final is not None
        msg, title = await _save_answer(conv.id, final)
        return ChatAnswer(
            message_id=msg.id,
            user_message_id=user_msg.id,
            content=final.content,
            sources=final.sources,
            intent=final.intent,
            conversation_title=title,
        )

    async def events() -> AsyncIterator[str]:
        try:
            async with SessionLocal() as sdb:
                async for ev in run_agent(sdb, provider, body.content, history):
                    if isinstance(ev, AgentEvent):
                        yield _sse(ev.kind, ev.data)
                    else:
                        msg, title = await _save_answer(conv.id, ev)
                        yield _sse("sources", {"sources": [s.model_dump(mode="json") for s in ev.sources]})
                        yield _sse(
                            "done",
                            {
                                "message_id": str(msg.id),
                                "user_message_id": str(user_msg.id),
                                "conversation_title": title,
                                "content": ev.content,
                                "intent": ev.intent,
                            },
                        )
        except Exception:
            logger.exception("chat stream failed")
            yield _sse("error", {"message": "The assistant could not generate an answer. Please retry."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
