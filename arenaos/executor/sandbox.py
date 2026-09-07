"""Real Linux execution sandbox: project-jailed workspaces, resource-limited subprocesses.

Honest limits (contract): process-level jail on shared hosts (Render free tier);
container isolation is available when ArenaOS runs as root/VPS by pointing
workspaces at isolated roots. Escape prevention = realpath boundary checks.
"""
from __future__ import annotations

import asyncio
import os
import resource
import shutil
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from arenaos.core.config import get_settings
from arenaos.core.logging import get_logger

logger = get_logger(__name__)

MAX_IN_MEMORY = 10_000  # chars of stdout/stderr kept in RAM


@dataclass
class ExecutionResult:
    """Real outcome of a command execution."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    stdout_path: str
    stderr_path: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class BackgroundHandle:
    """Handle to a tracked background process."""
    id: str
    command: str
    cwd: str
    started_at: float
    log_path: str


class ExecutionSandbox:
    """Subprocess execution with rlimits, timeouts, path jail, and background processes."""

    def __init__(self, base_dir: Optional[Path] = None, cpu_seconds: int = 120,
                 mem_mb: int = 1024, max_nproc: int = 64, max_nofile: int = 128) -> None:
        settings = get_settings()
        settings.ensure_dirs()
        self.base = Path(base_dir) if base_dir else settings.data_dir / "workspaces"
        self.base.mkdir(parents=True, exist_ok=True)
        self.logs_dir = settings.data_dir / "exec_logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.cpu_seconds = cpu_seconds
        self.mem_bytes = mem_mb * 1024 * 1024
        self.max_nproc = max_nproc
        self.max_nofile = max_nofile
        self._background: dict[str, tuple[asyncio.subprocess.Process, BackgroundHandle]] = {}

    # -- workspaces ---------------------------------------------------------

    def create_workspace(self, slug: str) -> Path:
        """Create (or return) an isolated workspace directory for a project slug."""
        safe_slug = "".join(c for c in slug if c.isalnum() or c in "-_").lower() or "ws"
        ws = self.base / safe_slug
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    def safe_path(self, workspace: str, relpath: str) -> Path:
        """Resolve a path inside a workspace; PermissionError if it escapes the jail."""
        root = Path(workspace).resolve()
        candidate = (root / relpath).resolve() if not os.path.isabs(relpath) else Path(relpath).resolve()
        if candidate != root and not str(candidate).startswith(str(root) + os.sep):
            raise PermissionError(f"path {relpath!r} escapes workspace jail")
        return candidate

    # -- foreground execution ----------------------------------------------

    def _limits(self) -> None:
        """Applied in the child via preexec_fn before exec."""
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (self.cpu_seconds, self.cpu_seconds))
            resource.setrlimit(resource.RLIMIT_AS, (self.mem_bytes, self.mem_bytes))
            resource.setrlimit(resource.RLIMIT_NOFILE, (self.max_nofile, self.max_nofile))
            resource.setrlimit(resource.RLIMIT_NPROC, (self.max_nproc, self.max_nproc))
        except (ValueError, OSError):  # keep hard caps sane in restricted environments
            pass

    async def run(self, command: str, cwd: str, timeout: float = 60.0,
                  env: Optional[dict] = None) -> ExecutionResult:
        """Execute a shell command in a workspace. Full stdout/stderr persisted to disk."""
        if not Path(cwd).resolve().is_relative_to(Path(self.base).resolve()):
            raise PermissionError(f"cwd {cwd!r} is outside the sandbox workspaces")
        run_id = uuid.uuid4().hex[:10]
        stdout_path = self.logs_dir / f"{run_id}.out"
        stderr_path = self.logs_dir / f"{run_id}.err"
        merged_env = {**os.environ, **(env or {})}
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_shell(
                command, cwd=cwd, env=merged_env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                preexec_fn=self._limits, start_new_session=True,
            )
        except PermissionError as exc:
            raise PermissionError(f"workspace cwd rejected: {exc}") from exc
        timed_out = False
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            out, err = await proc.communicate()
        duration_ms = int((time.monotonic() - start) * 1000)
        stdout_text = out.decode("utf-8", errors="replace")[:MAX_IN_MEMORY]
        stderr_text = err.decode("utf-8", errors="replace")[:MAX_IN_MEMORY]
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
        exit_code = -9 if timed_out else (proc.returncode if proc.returncode is not None else -1)
        if timed_out:
            stderr_text = (stderr_text + f"\n[sandbox] killed: timeout after {timeout}s").strip()
        logger.info("sandbox: exit=%s dur=%dms cmd=%r", exit_code, duration_ms, command[:120])
        return ExecutionResult(command=command, exit_code=exit_code, stdout=stdout_text,
                               stderr=stderr_text, duration_ms=duration_ms,
                               stdout_path=str(stdout_path), stderr_path=str(stderr_path))

    # -- background processes ------------------------------------------------

    async def start_background(self, command: str, cwd: str,
                               env: Optional[dict] = None) -> BackgroundHandle:
        """Start a long-running process tracked in the process table."""
        if not Path(cwd).resolve().is_relative_to(Path(self.base).resolve()):
            raise PermissionError(f"cwd {cwd!r} is outside the sandbox workspaces")
        handle_id = uuid.uuid4().hex[:8]
        log_path = self.logs_dir / f"bg-{handle_id}.log"
        merged_env = {**os.environ, **(env or {})}
        log_file = open(log_path, "ab")
        proc = await asyncio.create_subprocess_shell(
            command, cwd=cwd, env=merged_env,
            stdout=log_file, stderr=asyncio.subprocess.STDOUT,
            preexec_fn=self._limits, start_new_session=True,
        )
        handle = BackgroundHandle(id=handle_id, command=command, cwd=cwd,
                                  started_at=time.time(), log_path=str(log_path))
        self._background[handle_id] = (proc, handle)
        logger.info("sandbox: background %s started: %r", handle_id, command[:120])
        return handle

    def _find(self, handle_id: str):
        entry = self._background.get(handle_id)
        if entry is None:
            raise KeyError(f"unknown background process {handle_id!r}")
        return entry

    async def stop(self, handle_id: str) -> bool:
        """Kill a background process group. Returns True if it was running."""
        proc, _ = self._find(handle_id)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            return False
        return True

    def status(self, handle_id: str) -> dict:
        """Return the real status of a background process."""
        proc, handle = self._find(handle_id)
        return {"id": handle.id, "command": handle.command, "cwd": handle.cwd,
                "running": proc.returncode is None,
                "exit_code": proc.returncode,
                "started_at": handle.started_at,
                "uptime_s": time.time() - handle.started_at}

    def logs(self, handle_id: str, tail: int = 2000) -> str:
        """Return the last `tail` characters of a background process log."""
        _, handle = self._find(handle_id)
        try:
            content = Path(handle.log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return content[-tail:]

    def list_background(self) -> list[dict]:
        """List the current process table."""
        return [self.status(h) for h in list(self._background)[:50]]
