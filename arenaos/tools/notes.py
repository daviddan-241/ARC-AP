"""Obsidian-compatible knowledge vault: markdown notes + [[wikilinks]].

Files are plain .md in the vault dir — open the folder in Obsidian and it
just works (graph view, backlinks, search). Supports folders, YAML
frontmatter tags, wikilinks, backlink queries, and recursive search, so
the agent can build and navigate a real knowledge graph.
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
_TAG_LINE_RE = re.compile(r"^tags:\s*(.*)$", re.MULTILINE)


def _safe_folder(folder: str) -> Path:
    """Sanitize a folder arg into a real subpath — no traversal, no absolute."""
    parts = [p for p in re.split(r"[/\\]+", (folder or "").strip()) if p]
    clean = [re.sub(r"[^a-zA-Z0-9 _-]", "", p).strip() for p in parts]
    return Path(*[p for p in clean if p]) if any(clean) else Path()


def _frontmatter(tags: list[str]) -> str:
    if not tags:
        return ""
    return "tags: [" + ", ".join(t.strip() for t in tags if t.strip()) + "]\n\n"


def _note_paths(vault: Path, folder: str = "") -> list[Path]:
    base = vault / _safe_folder(folder)
    if not base.exists():
        return []
    return sorted(p for p in base.glob("**/*.md") if p.is_file())


class NoteWriteArgs(BaseModel):
    title: str = Field(description="note title (becomes the filename)")
    content: str = Field(description="markdown body; use [[wikilinks]] to connect notes")
    folder: str = Field(
        default="", description="optional subfolder, e.g. 'research' or 'projects/arena'")
    tags: list[str] = Field(
        default_factory=list, description="tags stored as YAML frontmatter (Obsidian-compatible)")


class NoteWriteTool(BaseTool):
    """Write a note to the Obsidian-compatible vault."""

    name = "note_write"
    description = (
        "Write/update a markdown note in the vault (Obsidian-compatible: "
        "wikilinks, folders, frontmatter tags). Links connect notes into a "
        "knowledge graph."
    )
    required_permissions = (Permission.FILESYSTEM_WRITE,)
    args_model = NoteWriteArgs

    async def execute(self, args: NoteWriteArgs, ctx: ToolContext) -> ToolResult:
        fname = re.sub(r"[^a-zA-Z0-9 _-]", "", args.title).strip().replace(" ", "-")
        if not fname:
            return ToolResult(ok=False, error="note needs a real title")
        folder = _safe_folder(args.folder)
        vault = _vault_dir(ctx)
        path = vault / folder / f"{fname}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        links = sorted(set(_LINK_RE.findall(args.content)))
        header = f"# {args.title}\n\n"
        path.write_text(
            _frontmatter(args.tags) + header + args.content.strip() + "\n",
            encoding="utf-8")
        rel = path.relative_to(vault)
        note = f"wrote {rel}"
        if links:
            note += f" (linked to: {', '.join(links)})"
        if args.tags:
            note += f" (tags: {', '.join(args.tags)})"
        return ToolResult(ok=True, output=note)


class NoteReadArgs(BaseModel):
    title: str
    folder: str = Field(default="", description="subfolder the note lives in, if any")


class NoteReadTool(BaseTool):
    """Read a note by title, wikilinks resolved as references."""

    name = "note_read"
    description = "Read one vault note by title (optionally in a folder)."
    required_permissions = (Permission.FILESYSTEM_READ,)
    args_model = NoteReadArgs

    async def execute(self, args: NoteReadArgs, ctx: ToolContext) -> ToolResult:
        fname = re.sub(r"[^a-zA-Z0-9 _-]", "", args.title).strip().replace(" ", "-")
        candidates = [
            _vault_dir(ctx) / _safe_folder(args.folder) / f"{fname}.md",
            _vault_dir(ctx) / _safe_folder(args.folder) / f"{args.title}.md",
        ]
        if not args.folder:  # fall back to a vault-wide lookup by stem
            candidates += [p for p in _note_paths(_vault_dir(ctx)) if p.stem == fname]
        path = next((c for c in candidates if c.is_file()), None)
        if path is None:
            return ToolResult(ok=False, error=f"no note titled {args.title!r}")
        text = path.read_text(encoding="utf-8")
        linked = sorted(set(_LINK_RE.findall(text)))
        return ToolResult(ok=True, output=text + (
            f"\n\n[links to: {', '.join(linked)}]" if linked else ""))


class NoteSearchArgs(BaseModel):
    query: str = Field(description="words to find across all notes (body, titles, tags)")
    folder: str = Field(default="", description="limit search to this subfolder")
    limit: int = Field(default=8, ge=1, le=30)


class NoteSearchTool(BaseTool):
    """Full-text search across the vault (recursive through folders)."""

    name = "note_search"
    description = (
        "Search every vault note (all folders) for a query — titles, body "
        "text, tags, wikilinks. Check the vault FIRST before re-creating "
        "knowledge."
    )
    required_permissions = (Permission.FILESYSTEM_READ,)
    args_model = NoteSearchArgs

    async def execute(self, args: NoteSearchArgs, ctx: ToolContext) -> ToolResult:
        vault = _vault_dir(ctx)
        q = args.query.lower()
        hits = []
        for md in _note_paths(vault, args.folder):
            body = md.read_text(encoding="utf-8")
            if q in body.lower():
                snippet_i = body.lower().find(q)
                snippet = re.sub(r"\s+", " ", body[max(0, snippet_i - 40):snippet_i + 80])
                rel = md.relative_to(vault)
                hits.append(f"{rel}: …{snippet}…")
            if len(hits) >= args.limit:
                break
        if not hits:
            return ToolResult(ok=True, output=f"no notes mention {args.query!r}")
        return ToolResult(ok=True, output="\n".join(hits))


class NoteListArgs(BaseModel):
    folder: str = Field(default="", description="list this subfolder; empty = whole vault")


class NoteListTool(BaseTool):
    """List the notes that actually exist — honest inventory, folders shown."""

    name = "note_list"
    description = (
        "List all vault notes (optionally one folder), showing each note's "
        "relative path and tags. Use this to see what knowledge exists "
        "before writing new notes."
    )
    required_permissions = (Permission.FILESYSTEM_READ,)
    args_model = NoteListArgs

    async def execute(self, args: NoteListArgs, ctx: ToolContext) -> ToolResult:
        vault = _vault_dir(ctx)
        paths = _note_paths(vault, args.folder)
        if not paths:
            return ToolResult(ok=True,
                              output="vault is empty here — no notes exist yet")
        lines = []
        for p in paths[:60]:
            body = p.read_text(encoding="utf-8")
            m = _TAG_LINE_RE.search(body)
            raw = m.group(1).strip().strip("[]").strip() if m else ""
            tags = f"  [{raw}]" if raw else ""
            lines.append(f"{p.relative_to(vault)}{tags}")
        return ToolResult(ok=True, output="\n".join(lines))


class NoteBacklinksArgs(BaseModel):
    title: str = Field(description="the note to find backlinks FOR")


class NoteBacklinksTool(BaseTool):
    """Which notes link TO this one — the Obsidian backlink panel, for real."""

    name = "note_backlinks"
    description = (
        "Find every vault note that wikilinks TO the given note — real "
        "backlinks across all folders. Use before restructuring or deleting "
        "a note to see what depends on it."
    )
    required_permissions = (Permission.FILESYSTEM_READ,)
    args_model = NoteBacklinksArgs

    async def execute(self, args: NoteBacklinksArgs, ctx: ToolContext) -> ToolResult:
        vault = _vault_dir(ctx)
        target = args.title.strip().lower()
        if not target:
            return ToolResult(ok=False, error="which note?")
        backlinks: list[str] = []
        for md in _note_paths(vault):
            body = md.read_text(encoding="utf-8")
            for link in _LINK_RE.findall(body):
                if link.strip().lower() == target:
                    line_no = body[:body.find(f"[[{link}]]")].count("\n") + 1
                    backlinks.append(f"{md.relative_to(vault)}:{line_no} → [[{link}]]")
                    break  # one hit per note is enough signal
        if not backlinks:
            return ToolResult(
                ok=True,
                output=f"no notes link to [[{args.title}]] — it may be an orphan "
                       "or not exist; note_list shows what does")
        return ToolResult(ok=True, output="\n".join(backlinks))
