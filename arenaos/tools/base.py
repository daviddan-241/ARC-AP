"""Tool system base classes. Every capability in ArenaOS is a BaseTool."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Optional

from pydantic import BaseModel

from arenaos.core.permissions import Permission, PermissionPolicy


@dataclass
class ToolResult:
    """Real outcome of a tool execution — never fabricated."""

    ok: bool
    output: str = ""
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "output": self.output, "error": self.error, "meta": self.meta}


class ToolContext:
    """Runtime context handed to every tool execution."""

    def __init__(
        self,
        workspace: str,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
        policy: Optional[PermissionPolicy] = None,
        env: Optional[Mapping[str, str]] = None,
        emit: Optional[Callable[..., Awaitable[None]]] = None,
        redact: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.workspace = workspace
        self.project_id = project_id
        self.task_id = task_id
        self.policy = policy
        self.env = dict(env or {})  # secrets injected here, never logged
        self._emit = emit
        self._redact = redact or (lambda s: s)

    async def emit(self, kind: str, data: dict[str, Any]) -> None:
        """Publish a live event (topic inferred by the registry: 'tool'/'exec')."""
        if self._emit:
            await self._emit(kind, data)

    def redact(self, text: str) -> str:
        """Strip secret values from text before it is stored or displayed."""
        return self._redact(text)


class BaseTool(ABC):
    """A single agent capability with declared permissions and a typed arg schema."""

    name: str = ""
    description: str = ""
    required_permissions: tuple[Permission, ...] = ()
    args_model: type[BaseModel] = BaseModel

    @abstractmethod
    async def execute(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        """Execute the tool. Success must reflect the real outcome."""

    def schema(self) -> dict[str, Any]:
        """JSON-schema description used for model tool-calling and the UI."""
        return {
            "name": self.name,
            "description": self.description,
            "permissions": [p.value for p in self.required_permissions],
            "args": self.args_model.model_json_schema(),
        }


class ToolRegistry:
    """In-process registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ValueError("tool must define a name")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise KeyError(f"unknown tool {name!r}")
        return self._tools[name]

    def list(self) -> list[BaseTool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]
