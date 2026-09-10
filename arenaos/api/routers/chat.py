"""Chat router: conversations + streaming messages through the live arena.ai session."""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import asyncio

from arenaos.api.deps import get_current_user
from arenaos.arena.base import MOODS
from arenaos.engine.agent_loop import AgentStep, MaxStepsExceeded, run_agent_loop
from arenaos.tools.base import ToolContext
from arenaos.core.logging import get_logger
from arenaos.core.security import redact
from arenaos.browser.errors import friendly_browser_error
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import Conversation, Message

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


class ConversationBody(BaseModel):
    title: str = "New chat"
    project_id: Optional[str] = None


class MessageBody(BaseModel):
    content: str
    mood: str = "uncensored"  # arena.base.MOODS key — set by the top-bar mood picker


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


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user=Depends(get_current_user)) -> dict:
    """Hard-delete a conversation and every message in it — real erasure
    (used by Private Chat, which promises 'fully erased')."""
    session: Session = _sessions()()
    try:
        session.query(Message).filter(Message.conversation_id == conversation_id).delete()
        session.query(Conversation).filter(Conversation.id == conversation_id).delete()
        session.commit()
    finally:
        session.close()
    return {"deleted": conversation_id}


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
            history_rows = (session_db.query(Message)
                            .filter(Message.conversation_id == conversation_id)
                            .order_by(Message.created_at, Message.id)
                            .limit(20).all())
            history = [{"role": r.role, "content": r.content} for r in history_rows[:-1]]
        finally:
            session_db.close()

        async def complete_fn(transcript: list[dict[str, str]]) -> str:
            messages = [ChatMessage(role=m["role"], content=m["content"]) for m in transcript]
            request_model = CompleteRequest(
                endpoint=ArenaEndpoint(name="arena-web", base_url="https://arena.ai"),
                messages=messages,
            )
            response = await provider.complete(request_model)
            return response.content

        tools = getattr(request.app.state, "tools", None)
        sandbox = getattr(request.app.state, "sandbox", None)
        full_text = ""
        model_name = "arena-web"

        if tools is None or sandbox is None:
            yield _sse({"kind": "error", "error": "tool registry not initialized"})
            return

        ws = sandbox.create_workspace(f"chat-{conversation_id}")
        ctx = ToolContext(workspace=str(ws), task_id=conversation_id,
                          env=request.app.state.secrets.inject_env())
        queue: asyncio.Queue = asyncio.Queue()

        async def on_step(step: AgentStep) -> None:
            if step.kind == "tool_call":
                await queue.put({"kind": "tool_call", "tool": step.tool, "args": step.args})
            elif step.kind == "tool_result":
                out = redact(str(step.result.get("output", "")))[:2000]
                from arenaos.observability.threat import scan_for_threats
                for t in scan_for_threats(out):
                    out = f"[THREAT-SHIELD] {t}\n{out}"
                await queue.put({"kind": "tool_result", "tool": step.tool,
                                 "ok": step.result.get("ok"),
                                 "output": out,
                                 "error": step.result.get("error", "")})

        async def produce() -> None:
            try:
                result = await run_agent_loop(
                    goal=body.content, registry=tools, ctx=ctx, complete=complete_fn,
                    mood_prelude=MOODS.get(body.mood, MOODS["uncensored"])["system_prelude"],
                    on_step=on_step, history=history,
                )
                await queue.put({"kind": "__final__", "text": result["summary"]})
            except MaxStepsExceeded as exc:
                await queue.put({"kind": "__error__", "error": str(exc)})
            except Exception as exc:
                logger.warning("agent loop failed: %s", exc)
                # Show one clean, honest sentence — never Playwright's raw
                # multi-line ASCII-art error box dumped straight into chat.
                await queue.put({"kind": "__error__",
                                 "error": f"arena.ai session error: {redact(friendly_browser_error(exc))}"})
            finally:
                await queue.put(None)

        producer = asyncio.ensure_future(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if item["kind"] == "__final__":
                    full_text = item["text"]
                    yield _sse({"kind": "token", "delta": full_text})
                    yield _sse({"kind": "done", "model": model_name})
                elif item["kind"] == "__error__":
                    yield _sse({"kind": "error", "error": item["error"]})
                    await producer
                    return
                else:
                    yield _sse(item)
            await producer
        finally:
            if not producer.done():
                producer.cancel()
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
