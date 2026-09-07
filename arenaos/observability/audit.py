"""Audit trail: every tool call and sensitive action, redacted before storage."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from arenaos.core.events import EventBus
from arenaos.core.security import redact
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import AuditLog, ToolCall


class Audit:
    """Persistent audit log + tool-call recorder."""

    def __init__(self, session_factory=None, bus: Optional[EventBus] = None) -> None:
        self._sessions = session_factory or get_sessionmaker()
        self._bus = bus

    def log(self, actor: str, action: str, resource: str = "", detail: Optional[dict] = None) -> None:
        """Write an audit entry. `detail` is redacted before storage."""
        session: Session = self._sessions()
        try:
            safe_detail = {k: redact(str(v)) if isinstance(v, str) else v
                           for k, v in (detail or {}).items()}
            session.add(AuditLog(actor=actor, action=action, resource=resource,
                                 detail=safe_detail))
            session.commit()
        finally:
            session.close()
        if self._bus:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._bus.publish("audit", action, safe_detail))
                else:
                    loop.run_until_complete(self._bus.publish("audit", action, safe_detail))
            except RuntimeError:
                pass

    def record_tool_call(self, tool: str, args: dict, ok: bool, result_summary: str,
                        duration_ms: Optional[int] = None, task_id: Optional[str] = None,
                        conversation_id: Optional[str] = None, permission: str = "",
                        model: str = "") -> int:
        """Persist a tool call with redacted args/summary. Returns the row id."""
        session: Session = self._sessions()
        try:
            safe_args = {k: redact(str(v)) if isinstance(v, str) else v for k, v in args.items()}
            row = ToolCall(tool=tool, args=safe_args, ok=ok, task_id=task_id,
                           conversation_id=conversation_id,
                           result_summary=redact(result_summary)[:4000],
                           duration_ms=duration_ms, permission=permission, model=model)
            session.add(row)
            session.commit()
            return row.id
        finally:
            session.close()

    def query(self, limit: int = 100, offset: int = 0, action: Optional[str] = None) -> list[dict]:
        """Query audit entries, newest first."""
        session: Session = self._sessions()
        try:
            q = session.query(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            if action:
                q = q.filter(AuditLog.action == action)
            rows = q.offset(offset).limit(limit).all()
            return [{"id": r.id, "actor": r.actor, "action": r.action, "resource": r.resource,
                     "detail": r.detail, "ts": r.created_at.isoformat() if r.created_at else None}
                    for r in rows]
        finally:
            session.close()

    def tool_calls(self, limit: int = 100, task_id: Optional[str] = None,
                   ok: Optional[bool] = None) -> list[dict]:
        """Query recorded tool calls, newest first."""
        session: Session = self._sessions()
        try:
            q = session.query(ToolCall).order_by(ToolCall.created_at.desc(), ToolCall.id.desc())
            if task_id:
                q = q.filter(ToolCall.task_id == task_id)
            if ok is not None:
                q = q.filter(ToolCall.ok == ok)
            rows = q.offset(0).limit(limit).all()
            return [{"id": r.id, "tool": r.tool, "ok": r.ok, "args": r.args,
                     "summary": r.result_summary, "duration_ms": r.duration_ms,
                     "task_id": r.task_id, "ts": r.created_at.isoformat() if r.created_at else None}
                    for r in rows]
        finally:
            session.close()
