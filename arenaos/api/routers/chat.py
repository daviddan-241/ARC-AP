"""Chat router: conversations + streaming messages through the live arena.ai session."""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from arenaos.api.deps import get_current_user
from arenaos.core.logging import get_logger
from arenaos.core.security import redact
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import Conversation, Message

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


class ConversationBody(BaseModel):
    title: str = "New chat"
    project_id: Optional[str] = None


class MessageBody(BaseModel):
    content: str


def _sessions():
    return get_sessionmaker()


@router.get("/conversations")
def list_conversations(user=Depends(get_current_user)) -> list[dict]:
    session: Session = _sessions()()
    try:
        rows = session.query(Conversation).order_by(Conversation.updated_at.desc()).limit(100).all()
        return [{"id": c.id, "title": c.title, "mode": c.mode,
                 "updated_at": c.updated_at.isoformat() if c.updated_at else None} for c in rows]
    finally:
        session.close()


@router.post("/conversations")
def create_conversation(body: ConversationBody, user=Depends(get_current_user)) -> dict:
    conv_id = uuid.uuid4().hex[:12]
    session: Session = _sessions()()
    try:
        session.add(Conversation(id=conv_id, title=body.title,
                                 project_id=body.project_id, mode="chat"))
        session.commit()
    finally:
        session.close()
    return {"id": conv_id, "title": body.title}


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, user=Depends(get_current_user)) -> list[dict]:
    session: Session = _sessions()()
    try:
        rows = (session.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at, Message.id).all())
        return [{"id": r.id, "role": r.role, "content": r.content,
                 "model": r.model,
                 "ts": r.created_at.isoformat() if r.created_at else None} for r in rows]
    finally:
        session.close()


def _persist_message(conversation_id: str, role: str, content: str, model: str = "") -> int:
    session: Session = _sessions()()
    try:
        row = Message(conversation_id=conversation_id, role=role,
                      content=content, model=model)
        session.add(row)
        session.commit()
        return row.id
    finally:
        session.close()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, body: MessageBody,
                       request: Request, user=Depends(get_current_user)):
    """Send a chat message; returns an SSE stream of real model events (or an honest error)."""
    provider = getattr(request.app.state, "provider", None)
    _persist_message(conversation_id, "user", redact(body.content))
    learned = []
    try:
        learned = request.app.state.autolearn.learn_from_message(body.content)
    except Exception:
        logger.exception("autolearn failed (non-fatal)")
    if learned:
        request.app.state.audit.log("autolearn", "memory_learned",
                                    detail={"facts": [f["content"] for f in learned]})

    async def stream():
        for fact in learned:
            yield _sse({"kind": "learned", "key": fact["key"], "content": fact["content"]})
        if provider is None:
            yield _sse({"kind": "error",
                        "error": "arena.ai browser transport not initialized — "
                                 "check server logs (Playwright/Chromium availability) or "
                                 "log in via Settings."})
            return
        from arenaos.arena.base import ArenaEndpoint, ChatMessage, CompleteRequest
        session_db: Session = _sessions()()
        try:
            history = (session_db.query(Message)
                       .filter(Message.conversation_id == conversation_id)
                       .order_by(Message.created_at, Message.id)
                       .limit(20).all())
            messages = [ChatMessage(role=r.role, content=r.content) for r in history]
        finally:
            session_db.close()
        request_model = CompleteRequest(
            endpoint=ArenaEndpoint(name="arena-web", base_url="https://arena.ai"),
            messages=messages,
        )
        full_text = ""
        model_name = "arena-web"
        try:
            async for event in provider.stream(request_model):
                if event.kind == "token":
                    full_text += event.delta
                    yield _sse({"kind": "token", "delta": event.delta})
                elif event.kind == "done":
                    full_text = event.data.get("content", full_text)
                    model_name = event.data.get("model", model_name)
                    yield _sse({"kind": "done", "model": model_name})
                elif event.kind == "error":
                    yield _sse({"kind": "error", "error": event.data.get("error", "unknown")})
                    return
        except Exception as exc:
            logger.warning("chat stream failed: %s", exc)
            yield _sse({"kind": "error", "error": f"arena.ai session error: {redact(str(exc))}"})
            return
        if full_text:
            _persist_message(conversation_id, "assistant", redact(full_text), model_name)
            try:
                model_facts = await request.app.state.autolearn.learn_with_model(
                    body.content, full_text, provider)
                for fact in model_facts:
                    yield _sse({"kind": "learned", "key": fact["key"], "content": fact["content"]})
            except Exception:
                logger.exception("model autolearn pass failed (non-fatal)")

    return StreamingResponse(stream(), media_type="text/event-stream")
