"""Self-hosting: run backend apps inside ARC's OWN Linux shell.

Danny's requirement, verbatim intent: "host them … and it host backends in
its shell — that's its Linux". Instead of only shipping apps to external
platforms (AppDeploy), ARC can host a backend it built as a real, tracked
process in its own Linux environment and expose it publicly through a
path-jailed reverse proxy at /hosted/<name>/ on ARC's own URL.

Everything here is real: real files written to disk, real subprocesses via
the ExecutionSandbox (rlimits, tracked handles, logs), a real port map
persisted in the settings table so the proxy survives process churn.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

from arenaos.core.config import get_settings
from arenaos.core.logging import get_logger
from arenaos.db.database import get_sessionmaker
from arenaos.db.models import Setting

logger = get_logger(__name__)

MAP_KEY = "selfhost_map"

# Entry points probed in order when auto-detecting a Python backend.
_PY_ENTRYPOINTS = ("main.py", "app.py", "server.py", "api.py", "index.py")


def hosted_base() -> Path:
    """Hosted apps live inside the sandbox workspaces dir (the ExecutionSandbox
    only spawns processes inside its workspace jail)."""
    base = Path(get_settings().data_dir) / "workspaces" / "hosted"
    base.mkdir(parents=True, exist_ok=True)
    return base


def app_dir(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in "-_").lower() or "app"
    d = hosted_base() / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_map() -> dict:
    session = get_sessionmaker()()
    try:
        row = session.get(Setting, MAP_KEY)
        if row is None or not row.value:
            return {}
        value = row.value
        return value if isinstance(value, dict) else json.loads(value)
    except Exception:
        return {}
    finally:
        session.close()


def save_map(mapping: dict) -> None:
    session = get_sessionmaker()()
    try:
        row = session.get(Setting, MAP_KEY)
        if row is None:
            session.add(Setting(key=MAP_KEY, value=mapping))
        else:
            row.value = mapping
        session.commit()
    finally:
        session.close()


def get_entry(name: str) -> dict | None:
    return load_map().get(name)


def set_entry(name: str, entry: dict) -> None:
    mapping = load_map()
    mapping[name] = entry
    save_map(mapping)


def remove_entry(name: str) -> None:
    mapping = load_map()
    if name in mapping:
        del mapping[name]
        save_map(mapping)


def next_free_port(start: int = 8600, limit: int = 200) -> int:
    """Real port probe — bind test against the loopback interface, so we
    never hand out a port something else in the shell already uses."""
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no free port in {start}-{start + limit}")


def port_alive(port: int, timeout: float = 0.4) -> bool:
    """Is something actually listening on this port right now?"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_start(directory: Path, port: int, command: str | None = None) -> str:
    """Real backend-type detection. Explicit `command` (with optional {port}
    placeholder) always wins; otherwise: node → pip/python → static."""
    if command:
        return command.replace("{port}", str(port))
    files = {p.name.lower() for p in directory.iterdir() if p.is_file()}

    if "package.json" in files:
        # npm apps conventionally honor PORT; we also pass --port for the
        # ones that use it. `npm start` must exist in their scripts.
        return ("npm install --no-audit --no-fund && "
                f"npm start -- --port {port}")

    py_entry = next((f for f in _PY_ENTRYPOINTS if f in files), None)
    has_reqs = "requirements.txt" in files
    if py_entry or has_reqs:
        reqs = (directory / "requirements.txt").read_text(
            encoding="utf-8", errors="ignore").lower() if has_reqs else ""
        install = "pip install -q -r requirements.txt && " if has_reqs else ""
        needs_uvicorn = ("fastapi" in reqs or "uvicorn" in reqs
                         or "starlette" in reqs)
        if py_entry:
            if needs_uvicorn and py_entry in ("main.py", "app.py"):
                stem = py_entry[:-3]
                return (f"{install}uvicorn {stem}:app --host 127.0.0.1 "
                        f"--port {port}")
            return f"{install}python {py_entry}"
        if needs_uvicorn:
            return (f"{install}uvicorn main:app --host 127.0.0.1 --port {port}")
        raise RuntimeError(
            "Python backend detected (requirements.txt present) but no "
            "main.py/app.py/server.py/api.py/index.py entrypoint and no "
            "uvicorn app found. Pass command='…' with the real start command "
            "(use {port} as the port placeholder).")

    if "index.html" in files:
        return f"python -m http.server {port} --bind 127.0.0.1"

    raise RuntimeError(
        "could not detect a backend type in that directory (no package.json, "
        "requirements.txt, python entrypoint, or index.html). Pass "
        "command='…' with the real start command ({port} = port placeholder).")
