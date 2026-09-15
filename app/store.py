"""ARC filesystem store — conversation, project, tool, workflow & knowledge memory.

No credentials ever stored here. PostgreSQL upgrade: swap the JSONL backends for
asyncpg; interface stays identical.
"""
import json, os, time
from typing import Optional
from .config import get_settings

S = get_settings()
ROOT = S.ARC_DATA_DIR

for sub in ["arc", "projects", "files", "tools", "tmp", "output", "knowledge"]:
    os.makedirs(os.path.join(ROOT, sub), exist_ok=True)


def _append(path: str, obj: dict):
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


def _read_all(path: str, limit: Optional[int] = None) -> list:
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    items = []
    for line in lines:
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return items[-limit:] if limit else items


# --- conversation memory ---
CONV = os.path.join(ROOT, "arc", "conversations.jsonl")

def save_message(session: str, role: str, content: str) -> str:
    mid = f"m{int(time.time()*1000)}"
    _append(CONV, {"id": mid, "session": session, "role": role,
                   "content": content, "ts": time.time()})
    return mid

def load_conversation(session: str, limit: int = 100) -> list:
    return [m for m in _read_all(CONV, limit) if m.get("session") == session]


# --- workflow memory (what ARC did & learned) ---
WF = os.path.join(ROOT, "arc", "workflow_memory.jsonl")

def append_workflow_memory(prompt: str, kind: str, outcome: str) -> str:
    wid = f"w{int(time.time()*1000)}"
    _append(WF, {"id": wid, "prompt": prompt[:300], "kind": kind, "outcome": outcome, "ts": time.time()})
    return wid

def load_memories(limit: int = 20) -> list:
    return [m.get("outcome", "") for m in _read_all(WF, limit)]


# --- project memory ---
def save_project(name: str, meta: dict) -> str:
    pid = f"p{int(time.time()*1000)}"
    _append(os.path.join(ROOT, "arc", "projects.jsonl"),
            {"id": pid, "name": name, **meta, "ts": time.time()})
    return pid

def load_projects() -> list:
    return _read_all(os.path.join(ROOT, "arc", "projects.jsonl"))


# --- knowledge memory (simple keyword index; no fake embeddings) ---
KNOW = os.path.join(ROOT, "knowledge", "index.jsonl")

def knowledge_index(text: str, source: str = "") -> str:
    kid = f"k{int(time.time()*1000)}"
    _append(KNOW, {"id": kid, "source": source, "text": text, "ts": time.time()})
    return kid

def knowledge_search(query: str, limit: int = 5) -> list:
    terms = [t.lower() for t in query.split() if len(t) > 2]
    hits = []
    for item in _read_all(KNOW):
        text = (item.get("text", "") + " " + item.get("source", "")).lower()
        score = sum(1 for t in terms if t in text)
        if score:
            hits.append({**item, "score": score})
    hits.sort(key=lambda x: -x["score"])
    return hits[:limit]


# --- sessions (recent chats) ---
def list_sessions(limit: int = 50) -> list:
    """Distinct sessions with last activity + preview."""
    items = _read_all(CONV)
    by_session = {}
    for m in items:
        s = m.get("session", "default")
        if s not in by_session:
            by_session[s] = {"session": s, "messages": 0, "preview": m.get("content", "")[:60], "ts": m.get("ts", 0)}
        by_session[s]["messages"] += 1
        by_session[s]["ts"] = m.get("ts", 0)
    out = sorted(by_session.values(), key=lambda x: -x["ts"])[:limit]
    return out

def delete_session(sid: str):
    items = _read_all(CONV)
    kept = [m for m in items if m.get("session") != sid]
    with open(CONV, "w") as f:
        for m in kept:
            f.write(json.dumps(m) + "\n")
