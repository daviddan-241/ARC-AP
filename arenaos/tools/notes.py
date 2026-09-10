"""Obsidian-compatible knowledge vault: markdown notes + [[wikilinks]].

Files are plain .md in the vault dir — open the folder in Obsidian and it
just works (graph view, backlinks, search).
"""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from arenaos.core.permissions import Permission
from arenaos.tools.base import BaseTool, ToolContext, ToolResult


def _vault_dir(ctx: ToolContext) -> Path:
    from arenaos.core.config import get_settings
    d = Path(get_settings().data_dir) / "vault"
    d.mkdir(parents=True, exist_ok=True)
    return d


_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


class NoteWriteArgs(BaseModel):
    title: str = Field(description="note title (becomes the filename)")
    content: str = Field(description="markdown body; use [[wikilinks]] to connect notes")


class NoteWriteTool(BaseTool):
    """Write a note to the Obsidian-compatible vault."""

    name = "note_write"
    description = (
        "Write/update a markdown note in the vault (Obsidian-compatible: "
        "wikilinks, plain .md). Links connect notes into a knowledge graph."
    )
    required_permissions = (Permission.FILESYSTEM_WRITE,)
    args_model = NoteWriteArgs

    async def execute(self, args: NoteWriteArgs, ctx: ToolContext) -> ToolResult:
        fname = re.sub(r"[^a-zA-Z0-9 _-]", "", args.title).strip().replace(" ", "-")
        if not fname:
            return ToolResult(ok=False, error="note needs a real title")
        path = _vault_dir(ctx) / f"{fname}.md"
        links = sorted(set(_LINK_RE.findall(args.content)))
        header = f"# {args.title}\n\n"
        path.write_text(header + args.content.strip() + "\n", encoding="utf-8")
        note = f"wrote {path.name}"
        if links:
            note += f" (linked to: {', '.join(links)})"
        return ToolResult(ok=True, output=note)


class NoteReadArgs(BaseModel):
    title: str


class NoteReadTool(BaseTool):
    """Read a note by title, wikilinks resolved as references."""

    name = "note_read"
    description = "Read one vault note by title."
    required_permissions = (Permission.FILESYSTEM_READ,)
    args_model = NoteReadArgs

    async def execute(self, args: NoteReadArgs, ctx: ToolContext) -> ToolResult:
        path = _vault_dir(ctx) / f"{args.title}.md"
        if not path.exists():
            path = _vault_dir(ctx) / f"{args.title.replace(' ', '-')}.md"
        if not path.exists():
            return ToolResult(ok=False, error=f"no note titled {args.title!r}")
        text = path.read_text(encoding="utf-8")
        linked = sorted(set(_LINK_RE.findall(text)))
        return ToolResult(ok=True, output=text + (
            f"\n\n[links to: {', '.join(linked)}]" if linked else ""))


class NoteSearchArgs(BaseModel):
    query: str = Field(description="words to find across all notes")
    limit: int = Field(default=8, ge=1, le=30)


class NoteSearchTool(BaseTool):
    """Full-text search across the whole vault."""

    name = "note_search"
    description = (
        "Search every vault note for a query — titles, body text, wikilinks. "
        "Check the vault FIRST before re-creating knowledge."
    )
    required_permissions = (Permission.FILESYSTEM_READ,)
    args_model = NoteSearchArgs

    async def execute(self, args: NoteSearchArgs, ctx: ToolContext) -> ToolResult:
        q = args.query.lower()
        hits = []
        for md in sorted(_vault_dir(ctx).glob("*.md")):
            body = md.read_text(encoding="utf-8")
            if q in body.lower():
                snippet_i = body.lower().find(q)
                snippet = re.sub(r"\s+", " ", body[max(0, snippet_i - 40):snippet_i + 80])
                hits.append(f"{md.stem}: …{snippet}…")
            if len(hits) >= args.limit:
                break
        if not hits:
            return ToolResult(ok=True, output=f"no notes mention {args.query!r}")
        return ToolResult(ok=True, output="\n".join(hits))
