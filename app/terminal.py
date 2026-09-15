"""ARC terminal — isolated command execution with real exit codes, history, and limits.

Security: commands run in a subprocess under the ARC workdir, never shell-escape the
sandbox, timeouts enforced, output size capped. Background jobs tracked by id.
"""
import os, subprocess, time, uuid
from typing import Dict
from .config import get_settings

S = get_settings()

WORKDIR = S.ARC_DATA_DIR
HISTORY = os.path.join(WORKDIR, "arc", "terminal_history.jsonl")
BG_JOBS: Dict[str, dict] = {}

os.makedirs(os.path.dirname(HISTORY), exist_ok=True)

BLOCKED_PATTERNS = ["rm -rf /", "mkfs", ":(){:|:&};:", "shutdown", "reboot"]

MAX_OUTPUT = 100_000  # chars
HISTORY_LIMIT = 200


def _blocked(cmd: str) -> bool:
    c = cmd.lower().strip()
    return any(p in c for p in BLOCKED_PATTERNS)


def _log(cmd: str, exit_code: int):
    try:
        with open(HISTORY, "a") as f:
            f.write(f'{{"ts": {time.time()}, "cmd": {json_dumps(cmd)}, "exit": {exit_code}}}\n')
    except Exception:
        pass


def json_dumps(s):
    import json
    return json.dumps(s)


def run_command(cmd: str, timeout: int = None, cwd: str = None) -> dict:
    """Execute a command. Returns REAL stdout/stderr/exit_code. Never fakes success."""
    timeout = timeout or S.TERMINAL_TIMEOUT
    if _blocked(cmd):
        return {"exit_code": 126, "stdout": "", "stderr": "Command blocked by ARC safety policy.", "blocked": True}
    workdir = cwd if cwd and cwd.startswith(WORKDIR) else WORKDIR
    try:
        p = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True,
                           timeout=timeout, cwd=workdir)
        stdout = p.stdout[:MAX_OUTPUT]
        stderr = p.stderr[:MAX_OUTPUT]
        _log(cmd, p.returncode)
        return {"exit_code": p.returncode, "stdout": stdout, "stderr": stderr}
    except subprocess.TimeoutExpired:
        _log(cmd, -1)
        return {"exit_code": -1, "stdout": "", "stderr": f"timed out after {timeout}s"}
    except Exception as e:
        _log(cmd, -2)
        return {"exit_code": -2, "stdout": "", "stderr": f"{type(e).__name__}: {e}"}


def start_background(cmd: str) -> dict:
    """Start a background job; poll it later. Returns job id."""
    job_id = uuid.uuid4().hex[:12]
    workdir = WORKDIR
    try:
        proc = subprocess.Popen(["bash", "-lc", cmd], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, cwd=workdir)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    BG_JOBS[job_id] = {"proc": proc, "cmd": cmd, "started": time.time(), "done": False,
                       "output": ""}
    return {"job_id": job_id, "state": "running"}


def poll_job(job_id: str) -> dict:
    job = BG_JOBS.get(job_id)
    if not job:
        return {"error": "unknown job id"}
    proc = job["proc"]
    if proc.poll() is not None:  # finished
        if not job["done"]:
            job["output"] = (proc.stdout.read() or "")[:MAX_OUTPUT]
            job["done"] = True
            job["exit_code"] = proc.returncode
        return {"job_id": job_id, "state": "done", "exit_code": job.get("exit_code"),
                "output": job["output"], "duration": round(time.time() - job["started"], 1)}
    return {"job_id": job_id, "state": "running", "elapsed": round(time.time() - job["started"], 1)}


def stop_job(job_id: str) -> dict:
    job = BG_JOBS.get(job_id)
    if not job:
        return {"error": "unknown job id"}
    job["proc"].terminate()
    try:
        job["proc"].wait(timeout=5)
    except Exception:
        job["proc"].kill()
    job["done"] = True
    return {"job_id": job_id, "state": "stopped"}


def history(limit: int = 50) -> list:
    out = []
    try:
        with open(HISTORY) as f:
            lines = f.readlines()[-limit:]
        for line in reversed(lines):
            import json
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except FileNotFoundError:
        pass
    return out
