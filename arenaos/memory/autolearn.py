"""Auto-learn: automatically extracts durable facts from chat exchanges.

Two real mechanisms:
1. Heuristic extraction (always on, deterministic, zero latency): detects
   self-statements of stable preference/fact ("my name is X", "I like X",
   "remember that X", ...) and stores them as long-term memory.
2. Optional model-assisted extraction (set AUTOLEARN_MODEL=1): after an
   exchange, asks the arena session to extract durable facts as JSON and
   stores them with source="autolearn:arena".

Everything dedupes against recent memories with the same key.
"""
from __future__ import annotations

import re
from typing import Optional

from arenaos.core.logging import get_logger
from arenaos.memory.store import MemoryStore

logger = get_logger(__name__)

# Deterministic extraction patterns over user messages. Keep tight — we only
# capture things the person actually said about themselves or asked to persist.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("profile.name", re.compile(
        r"(?i)\bmy name is ([A-Za-z][\w'\- ]{1,40})")),
    ("profile.location", re.compile(
        r"(?i)\bi(?:'m| am) (?:based|living|located) in ([\w ,'\-]{2,40})")),
    ("profile.language", re.compile(
        r"(?i)\bmy (?:favourite|favorite|preferred) language is ([\w #+\-]{1,20})")),
    ("preference", re.compile(
        r"(?i)\bi (?:really )?(?:like|love|prefer|enjoy) ([\w ,'\-]{2,60})")),
    ("preference.negative", re.compile(
        r"(?i)\bi (?:really )?(?:hate|dislike|don't like|do not like) ([\w ,'\-]{2,60})")),
    ("instruction", re.compile(
        r"(?i)\b(?:remember|note) that ([^.!?\n]{3,160})")),
    ("instruction", re.compile(
        r"(?i)\balways ([^.!?\n]{3,120})")),
    ("instruction.never", re.compile(
        r"(?i)\bnever ([^.!?\n]{3,120})")),
]

STOPWORDS = re.compile(r"(?i)^(?:it|this|that|them|those|you|to|a|an|the)\b")
NEGATIVE_FILTER = re.compile(
    r"(?i)^(?:you|it|this|that|we|they)\b.*")


def extract_facts(user_message: str) -> list[tuple[str, str]]:
    """Return (key, content) fact pairs detected in a user message."""
    facts: list[tuple[str, str]] = []
    text = user_message.strip()
    if len(text) > 2000:
        return facts
    for key, pattern in PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1).strip().rstrip(".,;:!?").strip()
            if not value or len(value) < 2 or NEGATIVE_FILTER.match(value):
                continue
            if STOPWORDS.match(value):
                continue
            facts.append((key, value))
    # hard cap: even a pattern-heavy message can't spam memory
    return facts[:5]


class AutoLearner:
    """Runs extraction on exchanges and persists new durable memories."""

    def __init__(self, store: MemoryStore, enabled: bool = True,
                 model_assisted: bool = False) -> None:
        self.store = store
        self.enabled = enabled
        self.model_assisted = model_assisted

    def learn_from_message(self, user_message: str) -> list[dict]:
        """Heuristic pass. Returns the memories actually stored (deduped)."""
        if not self.enabled:
            return []
        stored: list[dict] = []
        recent = self.store.search("", layer="long", limit=200)
        recent_contents = {m["content"].lower() for m in recent}
        for key, value in extract_facts(user_message):
            content = value
            if content.lower() in recent_contents:
                continue
            memory_id = self.store.add(layer="long", content=content, key=key,
                                       tags=["autolearn"], source="autolearn")
            stored.append({"id": memory_id, "key": key, "content": content})
            recent_contents.add(content.lower())
        if stored:
            logger.info("autolearn: stored %d facts", len(stored))
        return stored

    async def learn_with_model(self, user_message: str, assistant_message: str,
                               provider) -> list[dict]:
        """Model-assisted pass through the arena session (opt-in)."""
        if not (self.model_assisted and provider is not None):
            return []
        from arenaos.arena.base import ArenaEndpoint, ChatMessage, CompleteRequest
        request = CompleteRequest(
            endpoint=ArenaEndpoint(name="arena-web", base_url="https://arena.ai"),
            messages=[
                ChatMessage(role="system", content=(
                    "Extract durable facts about the user from this exchange. "
                    "Return a JSON array of {\"key\": \"...\", \"content\": \"...\"}. "
                    "Return [] if nothing durable. No commentary.")),
                ChatMessage(role="user", content=f"USER: {user_message}\nASSISTANT: {assistant_message[:2000]}"),
            ],
        )
        try:
            response = await provider.complete(request)
            import json
            text = response.content.strip()
            start, end = text.find("["), text.rfind("]")
            if start == -1 or end == -1:
                return []
            facts = json.loads(text[start:end + 1])
        except Exception as exc:
            logger.warning("autolearn model pass failed: %s", exc)
            return []
        stored: list[dict] = []
        for fact in facts[:5]:
            if not isinstance(fact, dict):
                continue
            content = str(fact.get("content", "")).strip()
            key = str(fact.get("key", "fact")).strip()[:60] or "fact"
            if len(content) < 3 or len(content) > 300:
                continue
            memory_id = self.store.add(layer="long", content=content, key=key,
                                       tags=["autolearn", "arena"], source="autolearn:arena")
            stored.append({"id": memory_id, "key": key, "content": content})
        return stored
