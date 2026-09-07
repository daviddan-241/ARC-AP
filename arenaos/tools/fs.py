"""Filesystem tools — all paths confined to the workspace jail."""
from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from arenaos.core.permissions import Permission
from arenaos.tools.base import BaseTool, ToolContext, ToolResult

MAX_READ = 1_000_000  # bytes


class ReadArgs(BaseModel):
    path: str


class WriteArgs(BaseModel):
    path: str
    content: str


class ListArgs(BaseModel):
    path: str = "."
    recursive: bool = True


class DeleteArgs(BaseModel):
    path: str


def _jail(ctx: ToolContext, relpath: str) -> Path:
    """Resolve a workspace-relative path or raise out-of-jail."""
    root = Path(ctx.workspace).resolve()
    candidate = (root / relpath).resolve() if not Path(relpath).is_absolute() else Path(relpath).resolve()
    if candidate != root and not str(candidate).startswith(str(root) + "/"):
        raise PermissionError(f"path {relpath!r} escapes workspace jail")
    return candidate


class ReadFileTool(BaseTool):
    name = "fs.read"
    description = "Read a text file inside the project workspace."
    required_permissions = (Permission.FILESYSTEM_READ,)
    args_model = ReadArgs

    async def execute(self, args: ReadArgs, ctx: ToolContext) -> ToolResult:
        try:
            path = _jail(ctx, args.path)
            if not path.is_file():
                return ToolResult(ok=False, error=f"not a file: {args.path}")
            if path.stat().st_size > MAX_READ:
                return ToolResult(ok=False, error=f"file too large ({path.stat().st_size} bytes, max {MAX_READ})")
            return ToolResult(ok=True, output=ctx.redact(path.read_text(encoding="utf-8", errors="replace")))
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))


class WriteFileTool(BaseTool):
    name = "fs.write"
    description = "Create or overwrite a text file inside the project workspace."
    required_permissions = (Permission.FILESYSTEM_WRITE,)
    args_model = WriteArgs

    async def execute(self, args: WriteArgs, ctx: ToolContext) -> ToolResult:
        try:
            path = _jail(ctx, args.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args.content, encoding="utf-8")
            return ToolResult(ok=True, output=f"wrote {len(args.content)} bytes to {args.path}",
                              meta={"files_changed": [args.path]})
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        except OSError as exc:
            return ToolResult(ok=False, error=f"write failed: {exc}")


class ListFilesTool(BaseTool):
    name = "fs.list"
    description = "List files/directories in the project workspace."
    required_permissions = (Permission.FILESYSTEM_READ,)
    args_model = ListArgs

    async def execute(self, args: ListArgs, ctx: ToolContext) -> ToolResult:
        try:
            root = _jail(ctx, args.path)
            if not root.exists():
                return ToolResult(ok=False, error=f"path does not exist: {args.path}")
            entries: list[str] = []
            iterator = root.rglob("*") if args.recursive else root.iterdir()
            for p in iterator:
                entries.append(str(p.relative_to(Path(ctx.workspace).resolve())))
                if len(entries) >= 500:
                    break
            return ToolResult(ok=True, output="\n".join(sorted(entries)) or "(empty)")
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))


class DeleteFileTool(BaseTool):
    name = "fs.delete"
    description = "Delete a file or directory inside the project workspace."
    required_permissions = (Permission.FILESYSTEM_DELETE,)
    args_model = DeleteArgs

    async def execute(self, args: DeleteArgs, ctx: ToolContext) -> ToolResult:
        try:
            path = _jail(ctx, args.path)
            if path.is_dir():
                shutil.rmtree(path)
                return ToolResult(ok=True, output=f"deleted directory {args.path}",
                                  meta={"files_changed": [args.path]})
            if path.is_file():
                path.unlink()
                return ToolResult(ok=True, output=f"deleted {args.path}",
                                  meta={"files_changed": [args.path]})
            return ToolResult(ok=False, error=f"no such file or directory: {args.path}")
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        except OSError as exc:
            return ToolResult(ok=False, error=f"delete failed: {exc}")
