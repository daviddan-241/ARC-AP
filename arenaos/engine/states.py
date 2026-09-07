"""Task state machine."""
from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED_ON_PERMISSION = "blocked_on_permission"
    WAITING_RETRY = "waiting_retry"
    DEBUG = "debug"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}

TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.PLANNING, TaskStatus.CANCELLED},
    TaskStatus.PLANNING: {TaskStatus.QUEUED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.WAITING_RETRY, TaskStatus.DEBUG,
                         TaskStatus.BLOCKED_ON_PERMISSION, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED_ON_PERMISSION: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.WAITING_RETRY: {TaskStatus.RUNNING, TaskStatus.QUEUED, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.DEBUG: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: {TaskStatus.QUEUED},
    TaskStatus.CANCELLED: set(),
}


def valid_transition(source: TaskStatus, target: TaskStatus) -> bool:
    """True if source -> target is a legal transition."""
    if source == target:
        return False
    return target in TRANSITIONS.get(source, set())
