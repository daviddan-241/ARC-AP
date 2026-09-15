"""ARC Colab bridge — real, honest compute delegation.

ARC queues jobs; a Google Colab runtime running ARC_Colab_Agent.ipynb polls,
claims a job, executes the Python code in the Colab VM, and posts the result
back. Colab only works while the user's notebook is running — the capability
matrix reports ONLINE only when a worker heartbeat arrived in the last 5 min.
"""
import json
import os
import time
import uuid

from . import config as S

WORKERS = os.path.join(S.DATA_DIR, "colab_workers.json")
JOBS = os.path.join(S.DATA_DIR, "colab_jobs.json")

ONLINE_WINDOW = 300  # seconds


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def register(name: str = "colab", gpu: str = "") -> dict:
    workers = _load(WORKERS)
    wid = str(uuid.uuid4())[:12]
    rec = {"id": wid, "name": name, "gpu": gpu, "first_seen": time.time(), "last_seen": time.time()}
    workers = [w for w in workers if w.get("id") != wid]
    workers.append(rec)
    _save(WORKERS, workers)
    return rec


def heartbeat(worker_id: str) -> bool:
    workers = _load(WORKERS)
    for w in workers:
        if w["id"] == worker_id:
            w["last_seen"] = time.time()
            _save(WORKERS, workers)
            return True
    return False


def online_worker() -> dict | None:
    workers = _load(WORKERS)
    fresh = [w for w in workers if time.time() - w.get("last_seen", 0) < ONLINE_WINDOW]
    return sorted(fresh, key=lambda w: -w.get("last_seen", 0))[0] if fresh else None


def create_job(title: str, code: str) -> dict:
    jobs = _load(JOBS)
    job = {"id": str(uuid.uuid4())[:12], "title": title, "code": code,
           "status": "pending", "worker": None, "result": None,
           "created": time.time(), "updated": time.time()}
    jobs.append(job)
    _save(JOBS, jobs)
    return job


def next_job(worker_id: str) -> dict | None:
    """Claim the oldest pending job for a worker (atomic enough at this scale)."""
    jobs = _load(JOBS)
    for j in jobs:
        if j["status"] == "pending":
            j["status"] = "running"
            j["worker"] = worker_id
            j["updated"] = time.time()
            _save(JOBS, jobs)
            return j
    return None


def submit_result(job_id: str, worker_id: str, ok: bool, output: str) -> dict | None:
    jobs = _load(JOBS)
    for j in jobs:
        if j["id"] == job_id and j["worker"] == worker_id:
            j["status"] = "done" if ok else "failed"
            j["result"] = output[:20000]
            j["updated"] = time.time()
            _save(JOBS, jobs)
            return j
    return None


def status() -> dict:
    jobs = _load(JOBS)
    w = online_worker()
    pending = sum(1 for j in jobs if j["status"] == "pending")
    running = sum(1 for j in jobs if j["status"] == "running")
    done = sum(1 for j in jobs if j["status"] in ("done", "failed"))
    recent = sorted(jobs, key=lambda j: -j["updated"])[:10]
    return {"worker_online": bool(w),
            "worker": {"name": w["name"], "gpu": w.get("gpu", "")} if w else None,
            "jobs": {"pending": pending, "running": running, "done": done},
            "recent": [{"id": j["id"], "title": j["title"], "status": j["status"],
                        "updated": j["updated"]} for j in recent]}


def jobs_detail() -> list:
    return sorted(_load(JOBS), key=lambda j: -j["updated"])[:50]
