"""ARC Ollama client — talks to BOTH:
  - native Ollama (any self-hosted endpoint: /api/generate, /api/tags)
  - Ollama Cloud / any OpenAI-compatible endpoint (ollama.com etc: /v1/chat/completions, /v1/models)

Auto-detects the protocol, lists REAL installed models, never fabricates inference.
"""
import os, json
from typing import Optional, AsyncGenerator
import httpx
from .config import get_settings

S = get_settings()


def _overlay() -> dict:
    """Runtime settings from the Settings UI (write-only secrets stay server-side)."""
    try:
        p = os.path.join(S.ARC_DATA_DIR, "arc", "settings.json")
        if os.path.exists(p):
            return json.load(open(p))
    except Exception:
        pass
    return {}


def _base() -> str:
    return _overlay().get("ollama_base_url") or S.OLLAMA_BASE_URL


def _key() -> str:
    return _overlay().get("ollama_api_key") or os.environ.get("OLLAMA_API_KEY", "")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if _key():
        h["Authorization"] = f"Bearer {_key()}"
    return h


async def _is_native() -> bool:
    base = _base().rstrip("/")
    if "ollama.com" in base:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{base}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def ollama_health() -> dict:
    base = _base().rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"{base}/api/version", headers=_headers())
            if r.status_code == 200:
                return {"state": "READY", "version": r.json().get("version", "?")}
    except Exception:
        pass
    # OpenAI-compatible probe (ollama.com answers /v1/models)
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"{base}/v1/models", headers=_headers())
            if r.status_code == 200:
                return {"state": "READY", "version": "cloud (OpenAI-compatible)"}
            return {"state": "ERROR", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"state": "OFFLINE", "detail": type(e).__name__}


async def list_models(wake_retry: bool = False) -> list:
    base = _base().rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{base}/api/tags", headers=_headers())
            if r.status_code == 200:
                return [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        # cold-started free-tier host: wake it, wait, retry once
        if wake_retry:
            import asyncio
            await asyncio.sleep(35)
            try:
                async with httpx.AsyncClient(timeout=30) as c:
                    r = await c.get(f"{base}/api/tags", headers=_headers())
                    if r.status_code == 200:
                        return [m.get("name", "") for m in r.json().get("models", [])]
            except Exception:
                pass
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{base}/v1/models", headers=_headers())
            if r.status_code == 200:
                return [m.get("id", "") for m in r.json().get("data", [])]
    except Exception:
        pass
    return []


async def detect_council() -> dict:
    """Resolve the council. Env > settings.json > auto-detect by family name.
    Only ever returns models that ACTUALLY exist on the endpoint."""
    ov = _overlay()
    installed = await list_models(wake_retry=True)

    def pick(*families) -> Optional[str]:
        for fam in families:
            for name in installed:
                if fam in name.lower():
                    return name
        return None

    env_p = S.ARC_MODEL_PRIMARY or ov.get("model_primary")
    env_r = S.ARC_MODEL_REASONING or ov.get("model_reasoning")
    env_c = S.ARC_MODEL_CRITIC or ov.get("model_critic")

    # spec families: qwen (primary/instruct), dolphin (critic), deepseek (reasoning/coding)
    primary = env_p or pick("qwen", "gpt-oss", "llama", "mistral", "gemma") or (installed[0] if installed else None)
    reasoning = env_r or pick("deepseek", "qwen", "gpt-oss", "llama") or primary
    critic = env_c or pick("dolphin", "qwen", "llama", "gemma") or primary
    return {"primary": primary, "reasoning": reasoning, "critic": critic, "installed": installed,
            "endpoint": _base()}


async def generate_text(model: str, prompt: str, system: Optional[str] = None,
                        num_predict: int = 1024, temperature: float = 0.7) -> str:
    if await _is_native():
        payload = {"model": model, "prompt": prompt, "stream": False,
                   "options": {"num_predict": num_predict, "temperature": temperature}}
        if system:
            payload["system"] = system
        base = _base().rstrip("/")
        import asyncio
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=300) as c:
                    r = await c.post(f"{base}/api/generate", json=payload, headers=_headers())
                    if r.status_code != 200:
                        raise RuntimeError(f"ollama HTTP {r.status_code}: {r.text[:200]}")
                    return r.json().get("response", "")
            except (httpx.ConnectError, httpx.ReadTimeout):
                if attempt == 0:
                    await asyncio.sleep(20)  # cold start / restart race
            except RuntimeError:
                raise
    # OpenAI-compatible (Ollama Cloud etc.)
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    base = _base().rstrip("/")
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post(f"{base}/v1/chat/completions",
                         json={"model": model, "messages": msgs, "stream": False,
                               "max_tokens": num_predict, "temperature": temperature},
                         headers=_headers())
        if r.status_code != 200:
            raise RuntimeError(f"model API HTTP {r.status_code}: {r.text[:200]}")
        return r.json()["choices"][0]["message"].get("content", "")


async def generate_stream(model: str, prompt: str, system: Optional[str] = None,
                          num_predict: int = 1024, temperature: float = 0.7) -> AsyncGenerator[str, None]:
    """Yields NDJSON lines (native format) so the UI token stream is uniform."""
    if await _is_native():
        payload = {"model": model, "prompt": prompt, "stream": True,
                   "options": {"num_predict": num_predict, "temperature": temperature}}
        if system:
            payload["system"] = system
        client = httpx.AsyncClient(timeout=300)
        try:
            async with client.stream("POST", f"{_base().rstrip('/')}/api/generate",
                                     json=payload, headers=_headers()) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"ollama HTTP {r.status_code}")
                async for line in r.aiter_lines():
                    if line.strip():
                        yield line
        finally:
            await client.aclose()
        return
    # OpenAI-compatible SSE → convert to native-ish NDJSON
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    client = httpx.AsyncClient(timeout=300)
    try:
        async with client.stream("POST", f"{_base().rstrip('/')}/v1/chat/completions",
                                 json={"model": model, "messages": msgs, "stream": True,
                                       "max_tokens": num_predict, "temperature": temperature},
                                 headers=_headers()) as r:
            if r.status_code != 200:
                raise RuntimeError(f"model API HTTP {r.status_code}")
            async for line in r.aiter_lines():
                if not line.startswith("data: ") or line.strip() == "data: [DONE]":
                    continue
                try:
                    d = json.loads(line[6:])
                    delta = d["choices"][0].get("delta", {}).get("content", "")
                    done = d["choices"][0].get("finish_reason") is not None
                    yield json.dumps({"response": delta, "done": done})
                except Exception:
                    continue
    finally:
        await client.aclose()
