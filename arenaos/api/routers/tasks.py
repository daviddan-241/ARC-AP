"""Tasks router: create, start, cancel, resume, approve, inspect."""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from arenaos.api.deps import get_current_user


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskBody(BaseModel):
    goal: str
    project_id: Optional[str] = None
    task_type: str = "general"
    mode: str = "autonomous"


def _engine(request: Request):
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="task engine not initialized")
    return engine


@router.get("")
def list_tasks(request: Request, status: Optional[str] = None,
               user=Depends(get_current_user)) -> list[dict]:
    return _engine(request).list_tasks(status=status)


@router.post("")
async def create_task(body: TaskBody, request: Request, user=Depends(get_current_user)) -> dict:
    task = _engine(request).create_task(goal=body.goal, project_id=body.project_id,
                                        task_type=body.task_type, mode=body.mode)
    _engine(request).start(task["id"])
    return task


@router.get("/{task_id}")
def get_task(task_id: str, request: Request, user=Depends(get_current_user)) -> dict:
    task = _engine(request).get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="no such task")
    return task


@router.get("/{task_id}/events")
def task_events(task_id: str, request: Request, user=Depends(get_current_user)) -> list[dict]:
    return _engine(request).get_events(task_id)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request, user=Depends(get_current_user)) -> dict:
    if not _engine(request).cancel(task_id):
        raise HTTPException(status_code=409, detail="task not cancellable")
    return {"ok": True}


@router.post("/{task_id}/approve")
async def approve_task(task_id: str, request: Request, user=Depends(get_current_user)) -> dict:
    if not _engine(request).approve(task_id):
        raise HTTPException(status_code=409, detail="task is not blocked on permission")
    return {"ok": True}


@router.post("/{task_id}/resume")
async def resume_task(task_id: str, request: Request, user=Depends(get_current_user)) -> dict:
    if not _engine(request).resume(task_id):
        raise HTTPException(status_code=409, detail="task not resumable")
    return {"ok": True}


@router.get("/{task_id}/stream")
async def stream_task(task_id: str, request: Request, user=Depends(get_current_user)):
    """SSE stream of live bus events for one task."""
    bus = request.app.state.bus

    async def generator():
        queue_events = []
        async for event in bus.subscribe(topics=["task"], replay=50):
            if event.get("task_id") == task_id:
                yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")
