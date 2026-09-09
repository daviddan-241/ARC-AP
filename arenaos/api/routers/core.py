"""Core router: projects, files, memory, processes, logs, settings, vault, status, events."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from arenaos.api.deps import get_current_user
from arenaos.core.config import get_settings
from arenaos.core.logging import get_logger
from arenaos.core.security import redact
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import Project, Setting

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["core"])

MAX_FILE_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------- projects

class ProjectBody(BaseModel):
    name: str
    description: str = ""
    git_url: str = ""


def _project(request: Request, project_id: str) -> Project:
    session: Session = get_sessionmaker()()
    try:
        row = session.get(Project, project_id)
        if row is None:
            raise HTTPException(status_code=404, detail="no such project")
        return row
    finally:
        session.close()


@router.get("/projects")
def list_projects(user=Depends(get_current_user)) -> list[dict]:
    session: Session = get_sessionmaker()()
    try:
        rows = session.query(Project).order_by(Project.created_at.desc()).all()
        return [{"id": p.id, "name": p.name, "slug": p.slug,
                 "workspace_path": p.workspace_path, "status": p.status} for p in rows]
    finally:
        session.close()


@router.post("/projects")
def create_project(body: ProjectBody, request: Request,
                   user=Depends(get_current_user)) -> dict:
    sandbox = request.app.state.sandbox
    slug = body.name.lower().replace(" ", "-")[:40] or "project"
    workspace = sandbox.create_workspace(slug)
    project_id = uuid.uuid4().hex[:12]
    session: Session = get_sessionmaker()()
    try:
        session.add(Project(id=project_id, name=body.name, slug=slug,
                            description=body.description, git_url=body.git_url,
                            workspace_path=str(workspace)))
        session.commit()
    finally:
        session.close()
    return {"id": project_id, "name": body.name, "workspace_path": str(workspace)}


def _workspace_of(request: Request, project_id: str) -> Path:
    project = _project(request, project_id)
    ws = Path(project.workspace_path)
    if not ws.is_dir():
        raise HTTPException(status_code=404, detail="project workspace missing on disk")
    return ws


def _jail(ws: Path, relpath: str) -> Path:
    candidate = (ws / relpath).resolve()
    if not str(candidate).startswith(str(ws.resolve()) + os.sep) and candidate != ws.resolve():
        raise HTTPException(status_code=400, detail="path escapes project workspace")
    return candidate


# ---------------------------------------------------------------- files

@router.get("/projects/{project_id}/files")
def list_files(project_id: str, request: Request, path: str = ".",
               user=Depends(get_current_user)) -> list[dict]:
    ws = _workspace_of(request, project_id)
    target = _jail(ws, path)
    entries = []
    for p in sorted(target.iterdir())[:500]:
        entries.append({"name": p.name, "dir": p.is_dir(),
                        "size": p.stat().st_size if p.is_file() else None})
    return entries


@router.get("/projects/{project_id}/files/content")
def read_file(project_id: str, request: Request, path: str,
              user=Depends(get_current_user)) -> dict:
    ws = _workspace_of(request, project_id)
    target = _jail(ws, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="no such file")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    return {"path": path, "content": redact(target.read_text(encoding="utf-8", errors="replace"))}


@router.put("/projects/{project_id}/files/content")
def write_file(project_id: str, request: Request, body: dict,
               user=Depends(get_current_user)) -> dict:
    path = body.get("path", "")
    content = body.get("content", "")
    ws = _workspace_of(request, project_id)
    target = _jail(ws, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "bytes": len(content)}


@router.delete("/projects/{project_id}/files")
def delete_file(project_id: str, request: Request, path: str,
                user=Depends(get_current_user)) -> dict:
    import shutil
    ws = _workspace_of(request, project_id)
    target = _jail(ws, path)
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()
    else:
        raise HTTPException(status_code=404, detail="no such file")
    return {"ok": True}


@router.post("/projects/{project_id}/files/upload")
async def upload_file(project_id: str, request: Request, file: UploadFile = File(...),
                      user=Depends(get_current_user)) -> dict:
    ws = _workspace_of(request, project_id)
    target = _jail(ws, file.filename or "upload.bin")
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"ok": True, "bytes": len(data)}


@router.get("/projects/{project_id}/files/download")
def download_file(project_id: str, request: Request, path: str,
                  user=Depends(get_current_user)) -> FileResponse:
    ws = _workspace_of(request, project_id)
    target = _jail(ws, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="no such file")
    return FileResponse(str(target), filename=target.name)


# ---------------------------------------------------------------- memory

class MemoryBody(BaseModel):
    layer: str
    content: str
    key: str = ""
    tags: list = []
    project_id: Optional[str] = None


@router.get("/memory")
def memory_search(q: str = "", layer: Optional[str] = None,
                  request: Request = None, user=Depends(get_current_user)) -> list[dict]:
    store = request.app.state.memory
    if q:
        return store.search(q, layer=layer)
    return store.export(layer=layer)


@router.post("/memory")
def memory_add(body: MemoryBody, request: Request, user=Depends(get_current_user)) -> dict:
    try:
        memory_id = request.app.state.memory.add(
            layer=body.layer, content=body.content, key=body.key,
            tags=body.tags, project_id=body.project_id, source="user")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": memory_id}


@router.delete("/memory/{memory_id}")
def memory_delete(memory_id: int, request: Request, user=Depends(get_current_user)) -> dict:
    if not request.app.state.memory.delete(memory_id):
        raise HTTPException(status_code=404, detail="no such memory")
    return {"ok": True}


@router.get("/memory/export")
def memory_export(request: Request, user=Depends(get_current_user)) -> list[dict]:
    return request.app.state.memory.export()


# ---------------------------------------------------------------- background processes

@router.get("/processes")
def list_processes(request: Request, user=Depends(get_current_user)) -> list[dict]:
    return request.app.state.sandbox.list_background()


@router.post("/processes/{handle_id}/stop")
async def stop_process(handle_id: str, request: Request, user=Depends(get_current_user)) -> dict:
    try:
        stopped = await request.app.state.sandbox.stop(handle_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such process")
    return {"ok": stopped}


@router.get("/processes/{handle_id}/logs")
def process_logs(handle_id: str, request: Request, user=Depends(get_current_user)) -> dict:
    try:
        return {"logs": request.app.state.sandbox.logs(handle_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="no such process")


# ---------------------------------------------------------------- logs / audit

@router.get("/logs/audit")
def audit_logs(request: Request, limit: int = 100, user=Depends(get_current_user)) -> list[dict]:
    return request.app.state.audit.query(limit=limit)


@router.get("/logs/tool-calls")
def tool_call_logs(request: Request, limit: int = 100,
                   user=Depends(get_current_user)) -> list[dict]:
    return request.app.state.audit.tool_calls(limit=limit)


# ---------------------------------------------------------------- settings + vault

class SettingBody(BaseModel):
    key: str
    value: object


class VaultBody(BaseModel):
    name: str
    kind: str = "token"
    value: str




# ---------------------------------------------------------------- tools registry

@router.get("/tools")
def tools_list(request: Request, user=Depends(get_current_user)) -> list[dict]:
    """Every real capability the agent can invoke, with its arg schema."""
    registry = getattr(request.app.state, "tools", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="tool registry not initialized")
    return registry.schemas()


@router.post("/tools/{name}/invoke")
async def tool_invoke(name: str, request: Request, body: dict,
                     user=Depends(get_current_user)) -> dict:
    """Run any registered tool directly from the UI — same real code path the agent uses."""
    registry = getattr(request.app.state, "tools", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="tool registry not initialized")
    from arenaos.tools.base import ToolContext
    try:
        tool = registry.get(name)
        args_obj = tool.args_model(**(body.get("args", {})))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown tool {name!r}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid args: {exc}")
    sandbox = request.app.state.sandbox
    ws = sandbox.create_workspace(f"invoke-{uuid.uuid4().hex[:8]}")
    ctx = ToolContext(workspace=str(ws), env=request.app.state.secrets.inject_env())
    result = await tool.execute(args_obj, ctx)
    return result.to_dict()


@router.get("/settings")
def get_settings_rows(user=Depends(get_current_user)) -> dict:
    session: Session = get_sessionmaker()()
    try:
        return {s.key: s.value for s in session.query(Setting).all()}
    finally:
        session.close()


@router.put("/settings")
def put_setting(body: SettingBody, user=Depends(get_current_user)) -> dict:
    session: Session = get_sessionmaker()()
    try:
        row = session.get(Setting, body.key)
        if row is None:
            row = Setting(key=body.key, value=body.value)
            session.add(row)
        else:
            row.value = body.value
        session.commit()
    finally:
        session.close()
    return {"ok": True}


@router.get("/vault")
def vault_list(request: Request, user=Depends(get_current_user)) -> list[dict]:
    return request.app.state.secrets.list()


@router.post("/vault")
def vault_set(body: VaultBody, request: Request, user=Depends(get_current_user)) -> dict:
    request.app.state.secrets.set(body.name, body.kind, body.value)
    return {"ok": True}


@router.delete("/vault/{name}")
def vault_delete(name: str, request: Request, user=Depends(get_current_user)) -> dict:
    if not request.app.state.secrets.delete(name):
        raise HTTPException(status_code=404, detail="no such credential")
    return {"ok": True}


# ---------------------------------------------------------------- status + live events

@router.get("/status")
def status(request: Request, user=Depends(get_current_user)) -> dict:
    settings = get_settings()
    session: Session = get_sessionmaker()()
    try:
        arena_row = session.get(Setting, "arena_web_session_status")
        arena_status = arena_row.value if arena_row else None
    finally:
        session.close()
    return {
        "transport": settings.arena_transport,
        "arena_provider": getattr(request.app.state.provider, "config").name
                          if request.app.state.provider else None,
        "arena_session_status": arena_status,
        "engine_ready": request.app.state.engine is not None,
    }


@router.get("/events")
async def live_events(request: Request, user=Depends(get_current_user)):
    """SSE stream of every bus event — powers the live activity panel."""
    bus = request.app.state.bus

    async def generator():
        async for event in bus.subscribe():
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")
