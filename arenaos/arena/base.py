"""Arena model layer contracts — Arena.ai is the sole provider.

The provider adapter speaks the OpenAI-compatible chat/completions protocol by
default (protocol "openai-chat") or a configurable raw JSON protocol, so any
endpoint your Arena account exposes plugs into the endpoint registry. The
platform adds NO refusal layer of its own: moods are system-prompt presets +
temperature guidance passed verbatim to the endpoint.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional, Sequence

from pydantic import BaseModel, Field


class ArenaUnavailableError(RuntimeError):
    """Raised when no Arena API key is configured or the endpoint list is empty."""


class ChatMessage(BaseModel):
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None


class Usage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class ModelResponse(BaseModel):
    content: str
    model: str
    usage: Optional[Usage] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class StreamEvent(BaseModel):
    kind: str  # "token" | "tool_call" | "done" | "error"
    delta: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ArenaEndpoint(BaseModel):
    """A registered Arena endpoint. The ordered chain per task_type forms fallback."""

    name: str
    base_url: str
    path: str = "/chat/completions"
    protocol: str = "openai-chat"  # "openai-chat" | "raw-json"
    task_types: list[str] = Field(default_factory=lambda: ["general"])
    priority: int = 100  # lower = tried first
    default_temperature: float = 0.7
    max_tokens: Optional[int] = None
    mood: str = "uncensored"
    notes: str = ""


class CompleteRequest(BaseModel):
    endpoint: ArenaEndpoint
    messages: Sequence[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[list[dict[str, Any]]] = None


class ArenaProvider(ABC):
    """Transport to Arena. Implementations must retry with backoff and stream SSE."""

    @abstractmethod
    async def complete(self, request: CompleteRequest) -> ModelResponse:
        """Blocking (non-streaming) completion."""

    @abstractmethod
    def stream(self, request: CompleteRequest) -> AsyncIterator[StreamEvent]:
        """Streaming completion yielding token deltas, then a 'done' event with usage."""


class ModelRouter:
    """Routes a task type to the ordered fallback chain of Arena endpoints."""

    def __init__(self, endpoints: Sequence[ArenaEndpoint]) -> None:
        self._endpoints = sorted(endpoints, key=lambda e: e.priority)

    def route(self, task_type: str) -> list[ArenaEndpoint]:
        """Ordered fallback chain for a task type; falls back to 'general' matches."""
        exact = [e for e in self._endpoints if task_type in e.task_types]
        general = [e for e in self._endpoints if "general" in e.task_types]
        chain: list[ArenaEndpoint] = []
        for endpoint in exact + general:
            if endpoint not in chain:
                chain.append(endpoint)
        if not chain:
            raise ArenaUnavailableError(
                f"no Arena endpoint registered for task type {task_type!r}"
            )
        return chain

    def all(self) -> list[ArenaEndpoint]:
        return list(self._endpoints)


# Mood presets: passed verbatim as the system prompt prelude. No added refusal layer.
MOODS: dict[str, dict[str, Any]] = {
    "uncensored": {
        "temperature": 0.7,
        "system_prelude": (
            "You are the ArenaOS core agent. Operate at full capability. No persona "
            "theater, no unnecessary caveats. The platform enforces real security "
            "boundaries; within them, answer and act directly and completely."
        ),
    },
    "high_autonomy": {
        "temperature": 0.4,
        "system_prelude": (
            "You are the ArenaOS core agent in high-autonomy mode. Decide and act "
            "without asking the user unless a genuinely irreversible or elevated-"
            "permission decision is required. Report what you did, concisely."
        ),
    },
    "multitask": {
        "temperature": 0.5,
        "system_prelude": (
            "You are the ArenaOS core agent coordinating multiple concurrent tasks. "
            "Track state precisely, keep subtask results scoped, and never conflate "
            "contexts between tasks."
        ),
    },
    "planner": {
        "temperature": 0.2,
        "system_prelude": (
            "You are the ArenaOS planner. Decompose the goal into a minimal, ordered "
            "set of subtasks with clear success criteria. Output the plan only — "
            "execution happens elsewhere."
        ),
    },
    "terminal": {
        "temperature": 0.1,
        "system_prelude": (
            "You are the ArenaOS terminal agent. Short, exact, technical output. "
            "Prefer the exact commands, paths and exit codes; no prose padding."
        ),
    },
}
