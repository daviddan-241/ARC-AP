"""Three memory layers: short (in-process), long, per-project (DB-backed, searchable)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from arenaos.db.database import get_sessionmaker
from arenaos.db.models import Memory

MAX_SHORT = 100


class ShortTermMemory:
    """In-process conversation buffer keyed by conversation id."""

    def __init__(self, max_messages: int = MAX_SHORT) -> None:
        self._max = max_messages
        self._store: dict[str, list[dict]] = {}

    def add(self, conversation_id: str, role: str, content: str) -> None:
        buffer = self._store.setdefault(conversation_id, [])
        buffer.append({"role": role, "content": content})
        if len(buffer) > self._max:
            del buffer[: len(buffer) - self._max]

    def get(self, conversation_id: str) -> list[dict]:
        return list(self._store.get(conversation_id, []))

    def clear(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)


class MemoryStore:
    """Persistent long/project memory with search, export, full CRUD."""

    def __init__(self, session_factory=None) -> None:
        self._sessions = session_factory or get_sessionmaker()
        self.short = ShortTermMemory()

    def add(self, layer: str, content: str, key: str = "", tags: Optional[list] = None,
            project_id: Optional[str] = None, source: str = "agent") -> int:
        """Store a memory entry. layer in {long, project}."""
        if layer not in ("long", "project"):
            raise ValueError("layer must be 'long' or 'project'")
        session: Session = self._sessions()
        try:
            row = Memory(layer=layer, project_id=project_id, key=key or "",
                         content=content, tags=tags or [], source=source)
            session.add(row)
            session.commit()
            return row.id
        finally:
            session.close()

    def get(self, memory_id: int) -> Optional[dict]:
        session: Session = self._sessions()
        try:
            row = session.get(Memory, memory_id)
            return self._to_dict(row) if row else None
        finally:
            session.close()

    def update(self, memory_id: int, content: Optional[str] = None,
               key: Optional[str] = None, tags: Optional[list] = None) -> bool:
        session: Session = self._sessions()
        try:
            row = session.get(Memory, memory_id)
            if row is None:
                return False
            if content is not None:
                row.content = content
            if key is not None:
                row.key = key
            if tags is not None:
                row.tags = tags
            session.commit()
            return True
        finally:
            session.close()

    def delete(self, memory_id: int) -> bool:
        session: Session = self._sessions()
        try:
            row = session.get(Memory, memory_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
        finally:
            session.close()

    def search(self, query: str, layer: Optional[str] = None,
               project_id: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Rank by exact-key match first, then substring matches on content."""
        session: Session = self._sessions()
        try:
            q = session.query(Memory)
            if layer:
                q = q.filter(Memory.layer == layer)
            if project_id:
                q = q.filter(Memory.project_id == project_id)
            rows = q.order_by(Memory.updated_at.desc()).limit(500).all()
            needle = query.lower()
            exact = [r for r in rows if r.key and r.key.lower() == needle]
            partial = [r for r in rows if needle in r.content.lower() and r not in exact]
            return [self._to_dict(r) for r in (exact + partial)[:limit]]
        finally:
            session.close()

    def export(self, layer: Optional[str] = None, project_id: Optional[str] = None) -> list[dict]:
        """Export memories as plain dicts (full data, for user download)."""
        session: Session = self._sessions()
        try:
            q = session.query(Memory).order_by(Memory.id)
            if layer:
                q = q.filter(Memory.layer == layer)
            if project_id:
                q = q.filter(Memory.project_id == project_id)
            return [self._to_dict(r) for r in q.all()]
        finally:
            session.close()

    @staticmethod
    def _to_dict(row: Memory) -> dict:
        return {"id": row.id, "layer": row.layer, "project_id": row.project_id,
                "key": row.key, "content": row.content, "tags": row.tags,
                "source": row.source,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None}
