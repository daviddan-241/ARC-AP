"""ARC — Autonomous Reasoning & Compute. FastAPI control plane.

Honest by construction: real states, real results, no fake success.
Auth: Bearer ARC_API_KEY when set.
"""
import os, json, asyncio
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import get_settings
from . import ollama, ires, capabilities, research, terminal, store, tasks, crypto, browser, colab, media

S = get_settings()
app = FastAPI(title="ARC", version="0.2.0",
              description="Autonomous Reasoning & Compute — mobile-first AI operating system control plane")


@app.on_event("startup")
async def _start():
    tasks.start_worker()


async def _check_auth(authorization: Optional[str]):
    if not S.ARC_API_KEY:
        return
    if not authorization or authorization != f"Bearer {S.ARC_API_KEY}":
        raise HTTPException(401, "invalid or missing API key")


# ---------- models ----------
class ChatIn(BaseModel):
    message: str
    session: str = "default"
    history: Optional[list] = None

class CmdIn(BaseModel):
    command: str
    timeout: Optional[int] = None
    background: bool = False
    job_id: Optional[str] = None

class ResearchIn(BaseModel):
    query: str

class FileIn(BaseModel):
    path: str
    content: Optional[str] = None
    action: str = "read"

class ColabIn(BaseModel):
    models: Optional[list] = None
    action: str                # register|heartbeat|result|job|status|jobs (worker actions unauth: register/heartbeat/result/next)
    worker_id: Optional[str] = None
    job_id: Optional[str] = None
    name: Optional[str] = None
    gpu: Optional[str] = None
    title: Optional[str] = None
    code: Optional[str] = None
    ok: Optional[bool] = None
    output: Optional[str] = None

class CryptoIn(BaseModel):
    action: str            # wallet|wallets|balance|coin|price
    label: Optional[str] = None
    name: Optional[str] = None
    symbol: Optional[str] = None
    supply: int = 1_000_000
    address: Optional[str] = None
    symbol_id: Optional[str] = None

class TaskIn(BaseModel):
    goal: str = ""
    task_id: Optional[str] = None
    action: str = "create"  # create|stop|list|get

class SettingsIn(BaseModel):
    ollama_base_url: Optional[str] = None
    ollama_api_key: Optional[str] = None     # write-only, never returned
    model_primary: Optional[str] = None
    model_reasoning: Optional[str] = None
    model_critic: Optional[str] = None
    max_task_steps: Optional[int] = None

class KnowledgeIn(BaseModel):
    text: str
    source: Optional[str] = ""
    query: Optional[str] = None


# ---------- core ----------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "arc", "version": app.version}


@app.get("/status")
async def status():
    o = await ollama.ollama_health()
    return {"arc": "READY", "ollama": o["state"],
            "models_installed": len(await ollama.list_models())}


@app.get("/capabilities")
async def caps(x_arc_admin: Optional[str] = Header(None)):
    admin = bool(S.ARC_ADMIN_KEY) and x_arc_admin == S.ARC_ADMIN_KEY
    return await capabilities.capabilities(admin=admin)


@app.get("/models")
async def models(authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    council = await ollama.detect_council()
    installed = council["installed"]
    declared = council.get("declared") or {}
    missing = [m for m in declared.values() if m and m not in installed]
    return {"arc": "online" if installed else "no models",
            "available": len(installed),
            "declared": declared,
            "active": {"primary": council["primary"],
                       "reasoning": council["reasoning"],
                       "critic": council["critic"]},
            "roles": {"primary": bool(council["primary"]),
                      "reasoning": bool(council["reasoning"]),
                      "critic": bool(council["critic"])},
            "note": ("declared council models not installed on this host: " + ", ".join(missing)
                     + " — ARC fell back to installed models. Connect a capable model host "
                       "(Colab GPU worker or paid instance) to activate them.")
                    if missing else None}


# ---------- sessions (recent chats) ----------
@app.get("/sessions")
async def sessions():
    return {"sessions": store.list_sessions()}


@app.get("/sessions/{sid}")
async def session(sid: str):
    return {"messages": store.load_conversation(sid, limit=200)}


@app.delete("/sessions/{sid}")
async def del_session(sid: str):
    store.delete_session(sid)
    return {"ok": True}


# ---------- chat ----------
@app.post("/chat")
async def chat(body: ChatIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    store.save_message(body.session, "user", body.message)
    answer, kind = "", "auto"
    async for ev in ires.chat_stream(body.message, body.history):
        try:
            d = json.loads(ev)
        except Exception:
            continue
        if d.get("event") == "token":
            answer += d.get("text", "")
        elif d.get("event") == "done":
            kind = d.get("activity_kind", "auto")
        elif d.get("event") == "error":
            raise HTTPException(502, d.get("detail", "ARC pipeline error"))
    store.save_message(body.session, "assistant", answer)
    return {"answer": answer, "activity_kind": kind}


@app.post("/chat/stream")
async def chat_stream(body: ChatIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    store.save_message(body.session, "user", body.message)

    async def gen():
        answer = ""
        async for ev in ires.chat_stream(body.message, body.history):
            try:
                d = json.loads(ev)
                if d.get("event") == "token":
                    answer += d.get("text", "")
            except Exception:
                pass
            yield ev
        if answer:
            store.save_message(body.session, "assistant", answer)

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------- research ----------
@app.post("/research")
async def do_research(body: ResearchIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    report, sources = await research.research_web(body.query)
    store.append_workflow_memory(body.query, "research", report[:400])
    return {"query": body.query, "report": report, "sources": sources}


# ---------- browser (hidden until asked) ----------
@app.post("/browse")
async def browse_ep(body: dict, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    url = body.get("url", "")
    action = body.get("action", "extract")  # extract|screenshot|history
    if action == "history":
        return {"history": browser.history()}
    if not url.startswith("http"):
        raise HTTPException(400, "url required")
    if action == "screenshot":
        return browser.screenshot(url, body.get("width", 390), body.get("height", 844))
    return await browser.extract(url)


# ---------- media lab: real image generation + image/video editing ----------
class ImageGenIn(BaseModel):
    prompt: str
    width: int = 1024
    height: int = 1024

@app.post("/media/generate")
async def media_generate(body: ImageGenIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    r = await media.generate_image(body.prompt, body.width, body.height)
    if "error" in r:
        raise HTTPException(502, r["error"])
    return r


@app.post("/media/upload")
async def media_upload(request: Request, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    form = await request.form()
    up = form.get("file")
    if not up:
        raise HTTPException(400, "file required (multipart form field 'file')")
    ext = (up.filename or "upload.bin").rsplit(".", 1)[-1].lower()
    path, media_url = media._new_path(ext if ext else "bin")
    data = await up.read()
    with open(path, "wb") as f:
        f.write(data)
    return {"path": path, "url": media_url, "bytes": len(data)}


class ImageEditIn(BaseModel):
    path: str
    action: str
    arg: Optional[str] = None

@app.post("/media/edit-image")
async def media_edit_image(body: ImageEditIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    real = os.path.realpath(body.path)
    if not real.startswith(os.path.realpath(media.MEDIA_DIR)) or not os.path.isfile(real):
        raise HTTPException(400, "unknown source path — upload the image first via /media/upload")
    r = media.edit_image(real, body.action, body.arg)
    if "error" in r:
        raise HTTPException(422, r["error"])
    return r


class VideoEditIn(BaseModel):
    path: str
    action: str
    arg: Optional[str] = None

@app.post("/media/edit-video")
async def media_edit_video(body: VideoEditIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    real = os.path.realpath(body.path)
    if not real.startswith(os.path.realpath(media.MEDIA_DIR)) or not os.path.isfile(real):
        raise HTTPException(400, "unknown source path — upload the video first via /media/upload")
    r = media.edit_video(real, body.action, body.arg)
    if "error" in r:
        raise HTTPException(422, r["error"])
    return r


@app.get("/media/library")
async def media_library(authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    return {"items": media.list_library()}


@app.get("/media/lib/{fname}")
async def media_lib_file(fname: str):
    path = os.path.realpath(os.path.join(media.MEDIA_DIR, fname))
    if not path.startswith(os.path.realpath(media.MEDIA_DIR)) or not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/media/browser/{fname}")
async def media_browser_file(fname: str):
    path = os.path.realpath(os.path.join(S.ARC_DATA_DIR, "output", "browser", fname))
    if not path.startswith(os.path.realpath(S.ARC_DATA_DIR)) or not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path, media_type="image/png")


# ---------- terminal ----------
@app.post("/terminal")
async def term(body: CmdIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    if body.background:
        return terminal.start_background(body.command)
    if body.job_id:
        return terminal.poll_job(body.job_id)
    return terminal.run_command(body.command, timeout=body.timeout)


@app.get("/terminal/history")
async def term_history(limit: int = 50, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    return terminal.history(limit)


# ---------- background tasks ----------
@app.post("/tasks")
async def tasks_ep(body: TaskIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    if body.action == "create":
        return tasks.create_task(body.goal)
    if body.action == "stop":
        return tasks.stop_task(body.task_id or "")
    if body.action == "get":
        t = tasks.get_task(body.task_id or "")
        return t or {"error": "unknown task"}
    return {"tasks": tasks.list_tasks()}


@app.get("/tasks")
async def tasks_get(authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    return {"tasks": tasks.list_tasks()}


# ---------- crypto lab ----------
@app.get("/colab/status")
async def colab_status():
    return colab.status()

@app.post("/colab")
async def colab_route(body: ColabIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    a = body.action
    if a == "register":
        return colab.register(body.name or "colab", body.gpu or "", models=body.models)
    if a == "heartbeat":
        ok = colab.heartbeat(body.worker_id or "", models=body.models)
        return {"ok": ok} if ok else JSONResponse({"error": "unknown worker"}, status_code=404)
    if a == "next":
        j = colab.next_job(body.worker_id or "")
        return {"job": j} if j else {"job": None}
    if a == "result":
        j = colab.submit_result(body.job_id or "", body.worker_id or "", bool(body.ok), body.output or "")
        return {"ok": True} if j else JSONResponse({"error": "job not found"}, status_code=404)
    if a == "job":
        if not body.code:
            return JSONResponse({"error": "code required"}, status_code=400)
        w = colab.online_worker()
        st = "queued" if w else "queued (no Colab runtime online — start ARC_Colab_Agent.ipynb to process)"
        j = colab.create_job(body.title or "untitled", body.code)
        return {"job_id": j["id"], "status": st, "worker_online": bool(w)}
    if a == "jobs":
        return {"jobs": colab.jobs_detail()}
    if a == "status":
        return colab.status()
    return JSONResponse({"error": "unknown action"}, status_code=400)

@app.post("/crypto")
async def crypto_ep(body: CryptoIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    if body.action == "wallet":
        return crypto.create_wallet(body.label or f"wallet-{len(crypto.list_wallets())+1}")
    if body.action == "wallets":
        return {"wallets": crypto.list_wallets()}
    if body.action == "balance":
        return await crypto.get_balance(body.address or "")
    if body.action == "coin":
        return crypto.create_coin(body.name or "ArcToken", body.symbol or "ARC", body.supply)
    if body.action == "price":
        import httpx
        gecko_id = body.symbol_id or ("bitcoin" if (body.symbol or "").upper().startswith("BTC") else (body.symbol or "ethereum").lower())
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.coingecko.com/api/v3/simple/price",
                            params={"ids": gecko_id, "vs_currencies": "usd", "include_24hr_change": "true"})
            if r.status_code == 200 and gecko_id in r.json():
                d = r.json()[gecko_id]
                return {"price": d.get("usd"), "change_pct": d.get("usd_24h_change"), "source": "coingecko"}
            raise HTTPException(r.status_code, f"coingecko: {r.text[:120]}")
    raise HTTPException(400, "action must be wallet|wallets|balance|coin|price")


# ---------- settings (secrets write-only) ----------
@app.get("/settings")
async def settings_get():
    ov = ollama._overlay()
    safe = {k: v for k, v in ov.items() if "key" not in k}
    return {"settings": safe, "has_api_key": bool(ov.get("ollama_api_key") or os.environ.get("OLLAMA_API_KEY")),
            "defaults": {"ollama_base_url": S.OLLAMA_BASE_URL}}


@app.post("/settings")
async def settings_put(body: SettingsIn):
    p = os.path.join(S.ARC_DATA_DIR, "arc", "settings.json")
    ov = ollama._overlay()
    for k, v in body.dict().items():
        if v is not None and k != "ollama_api_key" or (k == "ollama_api_key" and v):
            ov[k] = v
    with open(p, "w") as f:
        json.dump(ov, f)
    return {"ok": True, "saved": [k for k, v in body.dict().items() if v is not None]}


# ---------- files ----------
@app.post("/files")
async def files(body: FileIn, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    root = S.ARC_DATA_DIR
    target = os.path.realpath(os.path.join(root, body.path.lstrip("/")))
    if not target.startswith(os.path.realpath(root)):
        raise HTTPException(400, "path escapes workspace")
    if body.action == "write":
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write(body.content or "")
        return {"ok": True, "path": body.path, "bytes": len(body.content or "")}
    if body.action == "delete":
        if os.path.isfile(target):
            os.remove(target)
            return {"ok": True, "deleted": body.path}
        raise HTTPException(404, "not found")
    if body.action == "list":
        if not os.path.isdir(target):
            raise HTTPException(404, "not a directory")
        return {"path": body.path, "entries": sorted(os.listdir(target))[:500]}
    if not os.path.isfile(target):
        raise HTTPException(404, "not found")
    with open(target) as f:
        return {"path": body.path, "content": f.read()[:100000]}


# ---------- knowledge / projects / jobs / integrations ----------
@app.post("/knowledge/index")
async def kindex(body: KnowledgeIn):
    return {"id": store.knowledge_index(body.text, body.source or "")}

@app.post("/knowledge/search")
async def ksearch(body: KnowledgeIn):
    hits = store.knowledge_search(body.query or body.text)
    return {"hits": hits}

@app.post("/projects")
async def projects(body: dict):
    pid = store.save_project(body.get("name", "untitled"), body)
    return {"project_id": pid, "projects": store.load_projects()}

@app.get("/projects")
async def projects_get():
    return {"projects": store.load_projects()}

@app.post("/github")
async def github(body: dict):
    if not os.environ.get("GITHUB_TOKEN"):
        raise HTTPException(501, "GITHUB_TOKEN not configured on this host")
    import httpx
    headers = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=20) as c:
        if body.get("action", "search") == "search":
            r = await c.get("https://api.github.com/search/repositories", params={"q": body.get("query", "")}, headers=headers)
        else:
            r = await c.get(f"https://api.github.com{body.get('path', '/user')}", headers=headers)
        if r.status_code != 200:
            raise HTTPException(r.status_code, f"github: {r.text[:200]}")
        return r.json()

@app.post("/security-lab")
async def security_lab(body: dict, authorization: Optional[str] = Header(None)):
    await _check_auth(authorization)
    mode = body.get("mode", "")
    allowed = {"LOCAL", "LAB", "CTF", "USER-OWNED", "AUTHORIZED_BUG_BOUNTY", "AUTHORIZED_TEST"}
    if mode not in allowed:
        raise HTTPException(400, f"mode must be one of {sorted(allowed)}")
    target = body.get("target", "") or "127.0.0.1"
    result = terminal.run_command(
        f"getent hosts {target} 2>/dev/null; curl -sI --max-time 10 {target if target.startswith('http') else 'http://'+target} 2>&1 | head -20",
        timeout=20)
    return {"mode": mode, "target": target, "findings": result}


# ---------- UI ----------
_static = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
@app.get("/icon.png")
async def icon():
    return FileResponse(os.path.join(_static, "icon.png"), media_type="image/png")

@app.get("/manifest.json")
async def manifest():
    return FileResponse(os.path.join(_static, "manifest.json"), media_type="application/json")

app.mount("/ui", StaticFiles(directory=_static, html=True), name="ui")

@app.get("/")
async def root():
    return FileResponse(os.path.join(_static, "index.html"))


@app.exception_handler(Exception)
async def err_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": type(exc).__name__, "detail": str(exc)[:500]})
