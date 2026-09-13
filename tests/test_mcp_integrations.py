"""Real tests for the MCP integrations (Composio + AppDeploy).

Three layers, all honest:
1. Protocol: the StreamableMCPClient against an in-process MCP stub served
   over a real local socket — initialize handshake, JSON + SSE response
   modes, session header reuse, real error surfacing (401, JSON-RPC errors,
   tool isError payloads).
2. Tools: appdeploy/composio arg mapping and vault behavior with a stubbed
   client — including that the API key is never leaked into tool output.
3. LIVE (opt-in, RUN_LIVE_MCP=1): real calls to the live AppDeploy MCP
   server — free anonymous key provisioning and get_apps — plus the real
   Composio gateway's honest no-key error. Skipped by default so CI stays
   hermetic.
"""
import json
import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from arenaos.integrations.mcp_client import MCPError, StreamableMCPClient
from arenaos.tools.base import ToolContext

LIVE = os.environ.get("RUN_LIVE_MCP") == "1"


def ctx(name: str) -> ToolContext:
    return ToolContext(workspace="/tmp")


def make_mcp_stub(sse: bool = False, with_session: bool = False,
                  require_auth: bool = False) -> FastAPI:
    """In-process MCP server speaking the real 2025-03-26 streamable-http
    protocol, mirroring what the live AppDeploy server actually does
    (hand-verified against api-v2.appdeploy.ai/mcp)."""
    app = FastAPI()

    def respond(body: dict, rid, status: int = 200) -> Response:
        payload = {"jsonrpc": "2.0", "id": rid, **body}
        headers = {}
        if with_session and status == 200:
            headers["mcp-session-id"] = "sess-123"
        if sse and status == 200:
            text = "event: message\ndata: " + json.dumps(payload) + "\n\n"
            return Response(text, media_type="text/event-stream",
                            headers=headers)
        return JSONResponse(payload, status_code=status, headers=headers)

    @app.post("/mcp")
    async def mcp(request: Request):
        if require_auth and not request.headers.get("authorization"):
            return JSONResponse(
                {"error": "Authorization required",
                 "reason": "No Authorization: Bearer header on request"},
                status_code=401)
        body = await request.json()
        method, rid = body.get("method"), body.get("id", 0)
        if method == "initialize":
            return respond({"result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "stub", "version": "0.1"}}}, rid)
        if method == "notifications/initialized":
            return Response(status_code=202)
        if method == "tools/list":
            return respond({"result": {"tools": [{
                "name": "echo", "description": "echo the arguments",
                "inputSchema": {"type": "object"}}]}}, rid)
        if method == "tools/call":
            name = body["params"]["name"]
            arguments = body["params"].get("arguments", {})
            if name == "boom":
                return respond({"result": {
                    "content": [{"type": "text", "text": "kaboom"}],
                    "isError": True}}, rid)
            return respond({"result": {"content": [
                {"type": "text", "text": json.dumps(arguments)}]}}, rid)
        return respond({"error": {"code": -32601,
                                 "message": f"unknown {method}"}}, rid)

    return app


def serve(app: FastAPI) -> str:
    """Serve the stub on a real ephemeral port — real HTTP, same process."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(200):
        try:
            httpx.post(url, json={"jsonrpc": "2.0", "id": 0,
                                  "method": "initialize",
                                  "params": {}}, timeout=0.5)
            if not server.started:
                time.sleep(0.05)
                continue
            return url
        except httpx.HTTPError:
            time.sleep(0.05)
    raise RuntimeError("stub server never came up")


@pytest.fixture(scope="module")
def stub_url():
    return serve(make_mcp_stub())


@pytest.fixture(scope="module")
def sse_stub_url():
    return serve(make_mcp_stub(sse=True, with_session=True))


@pytest.fixture(scope="module")
def auth_stub_url():
    return serve(make_mcp_stub(require_auth=True))


@pytest.fixture
def vault():
    from arenaos.secrets.manager import SecretsManager
    sm = SecretsManager()
    yield sm
    for name in ("appdeploy_api_key", "composio_api_key"):
        try:
            sm.delete(name)
        except Exception:
            pass


# ------------------------------------------------------------- protocol layer

async def test_initialize_and_list_tools(stub_url):
    client = StreamableMCPClient(stub_url, api_key="k")
    info = await client.initialize()
    assert info["serverInfo"]["name"] == "stub"
    tools = await client.list_tools()
    assert [t["name"] for t in tools] == ["echo"]


async def test_sse_response_and_session_header(sse_stub_url):
    client = StreamableMCPClient(sse_stub_url, api_key="k")
    await client.initialize()
    assert client._session_id == "sess-123"  # captured from response headers
    out = await client.call_tool_text("echo", {"hello": "world"})
    assert json.loads(out) == {"hello": "world"}


async def test_missing_key_is_401_with_real_message(auth_stub_url):
    client = StreamableMCPClient(auth_stub_url)  # no api_key configured
    with pytest.raises(MCPError, match="[Aa]uthorization required"):
        await client.initialize()


async def test_tool_iserror_surfaces_as_mcperror(stub_url):
    client = StreamableMCPClient(stub_url, api_key="k")
    await client.initialize()
    with pytest.raises(MCPError, match="kaboom"):
        await client.call_tool("boom", {})


async def test_transport_failure_is_mcperror():
    client = StreamableMCPClient("http://127.0.0.1:1/mcp")
    with pytest.raises(MCPError, match="transport failure"):
        await client.initialize()


# ---------------------------------------------------------------- tool layer

async def test_appdeploy_unknown_action_is_honest():
    from arenaos.tools.appdeploy import AppDeployTool
    res = await AppDeployTool().execute(
        AppDeployTool.args_model(action="nah"), ctx("appdeploy"))
    assert not res.ok and "unknown action" in res.error


async def test_appdeploy_auto_provision_failure_is_honest(vault, monkeypatch):
    """v14.1 contract: a missing key now AUTO-provisions (it's everywhere,
    no manual step). When provisioning itself fails (offline, upstream
    down), the error is honest and still points at action='key'."""
    import arenaos.tools.appdeploy as ap

    async def _fail():
        raise MCPError("network unreachable in test")

    monkeypatch.setattr(ap, "provision_key", _fail)
    res = await ap.AppDeployTool().execute(
        ap.AppDeployTool.args_model(action="list"), ctx("appdeploy"))
    assert not res.ok
    assert "action='key'" in res.error  # the one-step fix is spelled out


async def test_appdeploy_deploy_requires_core_args(vault):
    from arenaos.tools.appdeploy import AppDeployTool
    vault.set("appdeploy_api_key", "api_key", "k")
    res = await AppDeployTool().execute(
        AppDeployTool.args_model(action="deploy"), ctx("appdeploy"))
    assert not res.ok and "app_name" in res.error


async def test_appdeploy_deploy_payload_mapping(vault, stub_url):
    from arenaos.tools import appdeploy as ad
    vault.set("appdeploy_api_key", "api_key", "k")
    calls = {}

    class FakeClient:
        async def call_tool_text(self, name, arguments):
            calls[name] = arguments
            return json.dumps(arguments)

    orig = ad.StreamableMCPClient
    ad.StreamableMCPClient = lambda *a, **k: FakeClient()
    try:
        res = await ad.AppDeployTool().execute(
            ad.AppDeployArgs(
                action="deploy", app_name="demo", app_type="frontend-only",
                template="html-static",
                files={"index.html": "<h1>hi</h1>"},
                intent="initial deploy"),
            ctx("appdeploy"))
    finally:
        ad.StreamableMCPClient = orig
    assert res.ok, res.error
    payload = calls["deploy_app"]
    assert payload["app_name"] == "demo"
    assert payload["app_type"] == "frontend-only"
    assert payload["frontend_template"] == "html-static"
    assert payload["files"] == [{"filename": "index.html",
                                 "content": "<h1>hi</h1>"}]
    assert payload["app_id"] is None  # null => create a new app


async def test_composio_key_stored_never_echoed(vault, stub_url):
    from arenaos.tools import composio as cp

    class FakeClient:
        async def initialize(self):
            return {"serverInfo": {"name": "composio"}}

    orig = cp.StreamableMCPClient
    cp.StreamableMCPClient = lambda *a, **k: FakeClient()
    try:
        res = await cp.ComposioTool().execute(
            cp.ComposioArgs(action="key", api_key="sk-secret-123"),
            ctx("composio"))
    finally:
        cp.StreamableMCPClient = orig
    assert res.ok, res.error
    assert "sk-secret-123" not in res.output  # the key is never echoed
    assert vault.get("composio_api_key") == "sk-secret-123"  # really stored


async def test_composio_without_key_gives_signup_path():
    from arenaos.secrets.manager import SecretsManager
    from arenaos.tools import composio as cp
    try:
        SecretsManager().delete("composio_api_key")
    except Exception:
        pass
    res = await cp.ComposioTool().execute(
        cp.ComposioArgs(action="list"), ctx("composio"))
    assert not res.ok
    assert "dashboard.composio.dev" in res.error  # the real fix path


# ------------------------------------------------------------- LIVE (opt-in)

@pytest.mark.skipif(not LIVE, reason="set RUN_LIVE_MCP=1 to hit real servers")
async def test_live_appdeploy_provision_and_list():
    from arenaos.tools import appdeploy as ad
    res = await ad.AppDeployTool().execute(
        ad.AppDeployArgs(action="key"), ctx("appdeploy"))
    assert res.ok, res.error
    assert "vault" in res.output.lower()
    assert "ak_" not in res.output  # the key itself never appears
    res = await ad.AppDeployTool().execute(
        ad.AppDeployArgs(action="list"), ctx("appdeploy"))
    assert res.ok, res.error
    assert "apps" in res.output.lower()


@pytest.mark.skipif(not LIVE, reason="set RUN_LIVE_MCP=1 to hit real servers")
async def test_live_composio_requires_real_key():
    from arenaos.secrets.manager import SecretsManager
    from arenaos.tools import composio as cp
    try:
        SecretsManager().delete("composio_api_key")
    except Exception:
        pass
    res = await cp.ComposioTool().execute(
        cp.ComposioArgs(action="list"), ctx("composio"))
    assert not res.ok
    assert "dashboard.composio.dev" in res.error
