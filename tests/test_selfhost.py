"""Real tests for v14.1 — the three things Danny asked to be made real:

1. Composio key "added once in settings stays even after restart":
   the vault persists in the DB (restarts/crashes) AND env bootstrap vars
   (Render dashboard) are re-imported on every boot (redeploys).
2. AppDeploy "it's everywhere … it carries it": a missing key
   auto-provisions a real free one on first use — no manual step anywhere.
3. Self-hosting backends "in its shell — that's its Linux": real
   subprocess hosting + the public /hosted/<name>/ reverse proxy, with an
   honest down-state after the process stops.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from arenaos.executor.sandbox import ExecutionSandbox
from arenaos.tools.base import ToolContext


def ctx(name: str = "selfhost-test") -> ToolContext:
    return ToolContext(workspace="/tmp")


# --------------------------------------------------------------------- vault

def test_composio_key_reseed_from_env_and_survives_restart(monkeypatch):
    """The 'add once, stays forever' contract. Env vars from the Render
    dashboard are re-imported into the encrypted vault on every boot; env
    wins when set, in-app entries are untouched when it is not."""
    from arenaos.secrets.manager import SecretsManager

    sm = SecretsManager()
    sm.delete("composio_api_key")  # start honest: not in the vault

    monkeypatch.setenv("COMPOSIO_API_KEY", "composio-live-key-1")
    out = sm.reseed_from_env()
    assert "COMPOSIO_API_KEY" in out["imported"]
    assert sm.get("composio_api_key") == "composio-live-key-1"

    # 'restart' = a brand-new manager instance reading the same DB
    assert SecretsManager().get("composio_api_key") == "composio-live-key-1"

    # env updates win on the next boot
    monkeypatch.setenv("COMPOSIO_API_KEY", "composio-live-key-2")
    sm.reseed_from_env()
    assert SecretsManager().get("composio_api_key") == "composio-live-key-2"

    # env removed → the in-vault key stays (ordinary restarts keep it)
    monkeypatch.delenv("COMPOSIO_API_KEY")
    out = sm.reseed_from_env()
    assert out["imported"] == []
    assert SecretsManager().get("composio_api_key") == "composio-live-key-2"

    sm.delete("composio_api_key")


# ------------------------------------------------------------------ appdeploy

def test_appdeploy_auto_provisions_a_key_when_missing(monkeypatch):
    """"It's everywhere": with NO key in the vault, any action still works —
    the tool auto-provisions a free key first, then calls the gateway."""
    import arenaos.tools.appdeploy as ap
    from arenaos.secrets.manager import SecretsManager

    sm = SecretsManager()
    sm.delete("appdeploy_api_key")
    calls = {"provision": 0, "gateway_key": None}

    async def fake_provision():
        calls["provision"] += 1
        sm.set("appdeploy_api_key", "token", "auto-provisioned-ad-key")
        return "AppDeploy API key provisioned and stored encrypted in the vault."

    class FakeGatewayClient:
        def __init__(self, url, api_key=None, timeout_s=None):
            calls["gateway_key"] = api_key

        async def call_tool_text(self, tool, args):
            return "apps: []"

    monkeypatch.setattr(ap, "provision_key", fake_provision)
    monkeypatch.setattr(ap, "StreamableMCPClient", FakeGatewayClient)

    res = asyncio.run(ap.AppDeployTool().execute(
        ap.AppDeployArgs(action="list"), ctx()))
    assert res.ok, res.error
    assert calls["provision"] == 1
    assert calls["gateway_key"] == "auto-provisioned-ad-key"
    assert "apps: []" in res.output
    # key never leaks into tool output
    assert "auto-provisioned-ad-key" not in res.output
    sm.delete("appdeploy_api_key")


# ------------------------------------------------------------------ detection

def test_detect_start_real_type_detection(tmp_path):
    from arenaos.hosting import detect_start

    # explicit command always wins, {port} replaced
    cmd = detect_start(tmp_path, 9001, command="uvicorn mymod:app --port {port}")
    assert cmd == "uvicorn mymod:app --port 9001"

    # node/npm
    (tmp_path / "package.json").write_text('{"scripts": {"start": "node s.js"}}')
    assert "npm install" in detect_start(tmp_path, 9002)
    (tmp_path / "package.json").unlink()

    # python + fastapi → uvicorn on the entrypoint
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn")
    (tmp_path / "main.py").write_text("app = None")
    cmd = detect_start(tmp_path, 9003)
    assert "uvicorn main:app" in cmd and "--port 9003" in cmd
    assert "pip install" in cmd

    # static html → http.server
    d2 = tmp_path / "static"
    d2.mkdir()
    (d2 / "index.html").write_text("<h1>hi</h1>")
    assert "http.server" in detect_start(d2, 9004)

    # nothing detectable → loud, honest error with the exact fix
    d3 = tmp_path / "empty"
    d3.mkdir()
    with pytest.raises(RuntimeError, match="command="):
        detect_start(d3, 9005)


# ---------------------------------------------------------------- self-hosting

def test_selfhost_real_process_and_public_proxy(client):
    """The full 'host backends in its shell' loop, all real: files written
    to the sandbox jail, a real `python -m http.server` process, the port
    map persisted in the DB, the public /hosted/<name>/ proxy serving the
    content, honest 502 after stop, restart from the saved directory."""
    from arenaos.hosting import get_entry, remove_entry
    from arenaos.tools.selfhost import SelfHostArgs, SelfHostTool

    sandbox = ExecutionSandbox()
    tool = SelfHostTool(sandbox)
    name = "selfhost-e2e"
    remove_entry(name)  # start honest

    res = asyncio.run(tool.execute(SelfHostArgs(
        action="host", name=name,
        files={"index.html": "<h1>ARC self-host OK</h1>"}), ctx()))
    assert res.ok, res.error
    assert "/hosted/selfhost-e2e/" in res.output

    entry = get_entry(name)
    assert entry and entry["port"] > 0

    # the PUBLIC proxy serves the real process output
    r = client.get("/hosted/selfhost-e2e/")
    assert r.status_code == 200, r.text
    assert "ARC self-host OK" in r.text

    # logs are real process logs
    res = asyncio.run(tool.execute(SelfHostArgs(action="logs", name=name), ctx()))
    assert res.ok

    # stop → the proxy honestly reports the process is down
    res = asyncio.run(tool.execute(SelfHostArgs(action="stop", name=name), ctx()))
    assert res.ok
    deadline = time.time() + 5
    while time.time() < deadline:
        r = client.get("/hosted/selfhost-e2e/")
        if r.status_code == 502:
            break
        time.sleep(0.2)
    assert r.status_code == 502
    assert "restart" in r.json()["detail"]

    # restart from the saved directory brings it back live
    res = asyncio.run(tool.execute(SelfHostArgs(action="restart", name=name), ctx()))
    assert res.ok, res.error
    r = client.get("/hosted/selfhost-e2e/")
    assert r.status_code == 200 and "ARC self-host OK" in r.text

    # cleanup: stop + remove the entry
    asyncio.run(tool.execute(SelfHostArgs(action="stop", name=name), ctx()))
    remove_entry(name)
    assert get_entry(name) is None


def test_proxy_unknown_app_is_honest_404(client):
    r = client.get("/hosted/never-hosted/whatever")
    assert r.status_code == 404
    assert "selfhost" in r.json()["detail"]
