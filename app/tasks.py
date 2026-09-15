"""ARC background tasks — real worker loop. Tasks keep working until stopped.

Auto-approve policy (editable in Settings):
  - terminal commands: auto-approved unless on the blocked list
  - package installs: auto-approved inside the workspace
  - external side effects (deploys, live trades, messages): always need explicit ask

Honest about the host: the loop runs while the process is awake (on Render free
tier, the service sleeps when idle — a keep-alive ping keeps it running).
"""
import json, time, uuid
from typing import Callable, Optional
from .config import get_settings
from . import terminal, store

S = get_settings()

TASKS_FILE = os.path.join(S.ARC_DATA_DIR, "arc", "tasks.jsonl") if (os := __import__("os")) else None
TASKS_DIR = os.path.join(S.ARC_DATA_DIR, "arc")
os.makedirs(TASKS_DIR, exist_ok=True)

MAX_STEPS_DEFAULT = 50  # runaway protection; user can stop anytime ("don't stop until I say")


def _write_task(task: dict):
    """Task store: one JSON file per task (simple, robust)."""
    with open(os.path.join(TASKS_DIR, f"task_{task['id']}.json"), "w") as f:
        json.dump(task, f)


def _read_task(tid: str) -> Optional[dict]:
    try:
        return json.load(open(os.path.join(TASKS_DIR, f"task_{tid}.json")))
    except Exception:
        return None


def create_task(goal: str, max_steps: int = None) -> dict:
    task = {"id": uuid.uuid4().hex[:12], "goal": goal, "state": "running",
            "steps": [], "created": time.time(), "max_steps": max_steps or MAX_STEPS_DEFAULT,
            "auto_approved": True}
    _write_task(task)
    return task


def list_tasks() -> list:
    out = []
    for fn in sorted(os.listdir(TASKS_DIR)):
        if fn.startswith("task_") and fn.endswith(".json"):
            t = json.load(open(os.path.join(TASKS_DIR, fn)))
            out.append({k: t[k] for k in ("id", "goal", "state", "created", "step_count") if k in t}
                       | {"step_count": len(t.get("steps", []))})
    return sorted(out, key=lambda x: -x["created"])


def add_step(tid: str, kind: str, detail: str, result: str = "") -> dict:
    task = _read_task(tid)
    if not task:
        return {"error": "unknown task"}
    task["steps"].append({"kind": kind, "detail": detail, "result": result[:2000], "ts": time.time()})
    real = [s for s in task["steps"] if s["kind"] != "waiting"]
    if len(real) >= task["max_steps"]:
        task["state"] = "max_steps_reached"
    _write_task(task)
    return task


def stop_task(tid: str) -> dict:
    task = _read_task(tid)
    if not task:
        return {"error": "unknown task"}
    task["state"] = "stopped"
    _write_task(task)
    return {"id": tid, "state": "stopped"}


def get_task(tid: str) -> Optional[dict]:
    return _read_task(tid)


def _clean(raw: str) -> str:
    """Strip reasoning tags (deepseek-r1 style) and markdown fences."""
    import re
    t = re.sub(r"<think>.*?</think>", "", raw, flags=re.S)
    return t.replace("```", "")


def _parse(line: str) -> dict:
    """Tolerant one-line plan parser for small models."""
    l = line.strip().strip("`").strip()
    up = l.upper()
    if up.startswith("TERMINAL"):
        return {"action": "terminal", "detail": l.split(":", 1)[1].strip() if ":" in l else ""}
    if up.startswith("RESEARCH"):
        return {"action": "research", "detail": l.split(":", 1)[1].strip() if ":" in l else ""}
    if up.startswith("DONE") or up.startswith("COMPLETE"):
        return {"action": "done", "detail": l.split(":", 1)[1].strip() if ":" in l else l}
    cmd_starts = ("touch ", "echo ", "mkdir ", "cd ", "curl ", "wget ", "apt", "pip", "python",
                  "node ", "git ", "cat ", "ls", "rm ", "cp ", "mv ", "sudo ", "chmod ", "npm", "sh ", "bash")
    if l.startswith(cmd_starts) or l.startswith("$"):
        return {"action": "terminal", "detail": l.lstrip("$").strip()}
    raise ValueError(f"unplannable: {l[:120]}")


# --- the worker: async loop that advances tasks ---
def start_worker():
    import asyncio, threading

    async def loop():
        from . import ollama
        while True:
            try:
                for fn in os.listdir(TASKS_DIR):
                    if not (fn.startswith("task_") and fn.endswith(".json")):
                        continue
                    task = json.load(open(os.path.join(TASKS_DIR, fn)))
                    if task["state"] != "running":
                        continue
                    # advance one step
                    council = await ollama.detect_council()
                    if not council["primary"]:
                        add_step(task["id"], "waiting", "No model endpoint reachable — pausing until back online")
                        continue
                    steps_so_far = [f'{s["kind"]}: {s["detail"]} -> {str(s.get("result",""))[:150]}'
                                   for s in task["steps"][-6:]]
                    prompt = (f"GOAL: {task['goal']}\n\n"
                              f"You are root; sudo is unavailable and unnecessary.\n"
                              f"Previous steps with results:\n" + "\n".join(steps_so_far) +
                              f"\n\nReply with exactly ONE line, nothing else:\n"
                              f"TERMINAL: <a linux command>  OR  RESEARCH: <search query>  OR  DONE: <final summary>")
                    try:
                        raw = await ollama.generate_text(council["primary"], prompt,
                            system="You are ARC's autonomous task executor. One line only.", num_predict=150)
                        line = _clean(raw).strip().splitlines()[0].strip()
                        plan = _parse(line)
                    except Exception:
                        add_step(task["id"], "waiting", "Model response not actionable yet; retrying")
                        continue
                    if plan.get("action") == "terminal":
                        res = terminal.run_command(plan["detail"], timeout=90)
                        add_step(task["id"], "computing", plan["detail"],
                                 f"exit {res['exit_code']}: {res['stdout'][:400] or res['stderr'][:200]}")
                    elif plan.get("action") == "research":
                        from .research import research_web
                        report, sources = await research_web(plan["detail"])
                        add_step(task["id"], "scouting", plan["detail"],
                                 f"{len(sources)} sources: {report[:400]}")
                    elif plan.get("action") == "done":
                        task = _read_task(task["id"])
                        task["state"] = "completed"
                        task["result"] = plan.get("detail", "")
                        _write_task(task)
                    else:
                        add_step(task["id"], "waiting", f"Unplannable action: {str(plan)[:200]}")
            except Exception:
                pass
            await asyncio.sleep(4)  # cooperative loop; no busy spin

    threading.Thread(target=lambda: asyncio.new_event_loop().run_until_complete(loop()),
                     daemon=True).start()
