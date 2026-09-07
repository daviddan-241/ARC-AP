"""In-process async pub/sub event bus with bounded history.

Every state change, tool call and execution publishes here. The audit log,
the live UI and the SSE streams all consume the same events.
"""
from __future__ import annotations

import asyncio
import itertools
import time
from collections import deque
from typing import Any, AsyncIterator, Iterable

TOPICS: tuple[str, ...] = (
    "task",
    "chat",
    "tool",
    "exec",
    "plugin",
    "deploy",
    "notify",
    "audit",
    "log",
)


class EventBus:
    """Async pub/sub. Slow consumers drop events rather than blocking the bus."""

    def __init__(self, history_size: int = 1000) -> None:
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._subs: dict[int, tuple[set[str], asyncio.Queue]] = {}
        self._ids = itertools.count(1)
        self._lock = asyncio.Lock()

    async def publish(
        self, topic: str, kind: str, data: dict[str, Any] | None = None, task_id: str | None = None
    ) -> dict[str, Any]:
        """Publish an event to all matching subscribers and the history buffer."""
        if topic not in TOPICS:
            raise ValueError(f"unknown topic {topic!r}; expected one of {TOPICS}")
        event = {
            "id": f"{next(self._ids)}-{int(time.time() * 1000)}",
            "topic": topic,
            "kind": kind,
            "data": data or {},
            "task_id": task_id,
            "ts": time.time(),
        }
        self._history.append(event)
        async with self._lock:
            subs = list(self._subs.values())
        for topics, queue in subs:
            if topic in topics:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:  # slow consumer: drop, never block
                    pass
        return event

    def publish_threadsafe(
        self, loop: asyncio.AbstractEventLoop, topic: str, kind: str,
        data: dict[str, Any] | None = None, task_id: str | None = None,
    ) -> None:
        """Publish from a worker thread onto the running event loop."""
        asyncio.run_coroutine_threadsafe(self.publish(topic, kind, data, task_id), loop)

    async def subscribe(
        self, topics: Iterable[str] | None = None, replay: int = 0
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to topics (all by default). `replay` replays up to N recent events."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        sub_topics = set(topics) if topics else set(TOPICS)
        sub_id = next(self._ids)
        self._subs[sub_id] = (sub_topics, queue)
        for event in list(self._history)[-replay:]:
            if event["topic"] in sub_topics:
                queue.put_nowait(event)
        try:
            while True:
                event = await queue.get()
                if event.get("__end__"):
                    break
                yield event
        finally:
            self._subs.pop(sub_id, None)

    async def close(self) -> None:
        """Signal all subscribers to stop."""
        for topics, queue in list(self._subs.values()):
            queue.put_nowait({"__end__": True})
        self._subs.clear()
