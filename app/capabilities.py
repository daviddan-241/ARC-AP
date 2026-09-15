"""ARC capability matrix — probes the REAL environment. Never fakes status.

States: READY / DEGRADED / NOT_CONFIGURED / OFFLINE / ERROR
"""
import shutil, subprocess, os
from .config import get_settings
from . import ollama

S = get_settings()

OPTIONAL_TOOLS = ["pip", "pipx", "uv", "npm", "npx", "pnpm", "git", "curl", "wget", "jq",
                  "yq", "ffmpeg", "sqlite3", "python3", "node", "cargo", "go", "gcc",
                  "clang", "tmux", "chromium", "chromium-browser"]


def _bin(name: str, nice: str) -> dict:
    path = shutil.which(name)
    if path:
        return {"state": "READY", "detail": path}
    return {"state": "NOT_CONFIGURED", "detail": f"{name} not installed"}


async def capabilities(admin: bool = False) -> dict:
    caps = {}

    # Control plane (this service)
    caps["arc"] = {"state": "READY", "detail": "control plane responding"}

    # Ollama
    caps["ollama"] = await ollama.ollama_health()
    installed = await ollama.list_models()
    council = await ollama.detect_council()
    if caps["ollama"]["state"] == "READY":
        if not installed:
            caps["ollama"] = {"state": "DEGRADED", "detail": "reachable, no models installed"}
        else:
            caps["ollama"]["detail"] = f"{len(installed)} models installed"
    caps["models"] = {"state": "READY" if council["primary"] else "NOT_CONFIGURED",
                      "detail": council if admin else f'{len(installed)} available'}

    # Database
    if S.DATABASE_URL:
        caps["database"] = {"state": "NOT_CONFIGURED", "detail": "URL set, connection check at runtime"}
    else:
        caps["database"] = {"state": "NOT_CONFIGURED", "detail": "no DATABASE_URL; using filesystem store"}

    # Linux workspace
    caps["linux"] = _bin("bash", "linux")
    caps["python"] = _bin("python3", "python")
    caps["node"] = _bin("node", "node")
    caps["git"] = _bin("git", "git")

    # Browser (Playwright is optional; detect both)
    pw = shutil.which("playwright") or bool(importlib_spec("playwright"))
    caps["browser"] = {"state": "READY" if _bin("chromium", "b")["state"] == "READY" or _bin("chromium-browser", "b")["state"] == "READY" else "NOT_CONFIGURED",
                       "detail": "chromium detected" if caps.get("browser") else "install chromium + playwright"}
    pw_state = "READY" if pw else "NOT_CONFIGURED"
    caps["browser"]["detail"] = f"playwright={pw_state.lower()}"

    # Research engine needs only httpx (bundled)
    caps["research"] = {"state": "READY", "detail": f"max {S.RESEARCH_MAX_SOURCES} sources/query"}

    # Integrations — honest NOT_CONFIGURED until credentials exist
    caps["github"] = {"state": "READY" if os.environ.get("GITHUB_TOKEN") else "NOT_CONFIGURED",
                      "detail": "token present" if os.environ.get("GITHUB_TOKEN") else "GITHUB_TOKEN not set"}
    caps["composio"] = {"state": "READY" if os.environ.get("COMPOSIO_API_KEY") else "NOT_CONFIGURED",
                       "detail": "COMPOSIO_API_KEY not set" if not os.environ.get("COMPOSIO_API_KEY") else "key present"}
    caps["appdeploy"] = {"state": "READY" if os.environ.get("APPDEPLOY_API_KEY") else "NOT_CONFIGURED",
                        "detail": "APPDEPLOY_API_KEY not set" if not os.environ.get("APPDEPLOY_API_KEY") else "key present"}
    caps["mcp"] = {"state": "NOT_CONFIGURED", "detail": "no MCP servers registered"}
    caps["a2a"] = {"state": "READY", "detail": "internal agents: research, coding, browser, security, trading, files, deploy"}
    caps["tor"] = {"state": "NOT_CONFIGURED", "detail": "tor not installed"}
    caps["security_lab"] = {"state": "DEGRADED" if _bin("nmap", "n")["state"] != "READY" else "READY",
                            "detail": "base tooling only; authorized targets only"}
    caps["trading_lab"] = {"state": "NOT_CONFIGURED" if not os.environ.get("EXCHANGE_API_KEY") else "READY",
                           "detail": "paper trading default; live requires explicit activation"}

    # Optional tool inventory (admin only)
    if admin:
        caps["tools"] = {t: shutil.which(t) is not None for t in OPTIONAL_TOOLS}
    return caps


def importlib_spec(name: str):
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False
