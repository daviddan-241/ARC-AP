"""Real MCP (Model Context Protocol) client over Streamable HTTP.

This is the actual wire protocol used by modern MCP servers (initialize →
notifications/initialized → tools/list → tools/call), implemented with httpx
against the official 2025-03-26 streamable-http transport:

  POST <endpoint>  Content-Type: application/json
  Accept: application/json, text/event-stream
  Authorization: Bearer <key>            (when a key is configured)
  Mcp-Session-Id: <id>                  (when the server issues one)

Servers may answer either with plain JSON or with an SSE stream; both are
handled. JSON-RPC error objects surface as MCPError with the real server
message — never a generic "failed".

Live-verified against the real AppDeploy MCP server (api-v2.appdeploy.ai/mcp)
and the real Composio gateway (connect.composio.dev/mcp) — see
tests/test_mcp_integrations.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx


class MCPError(Exception):
    """A real error from the MCP layer: transport, protocol, or server-side."""


@dataclass
class StreamableMCPClient:
    """One client per MCP server endpoint. Async, thread-safe per task."""

    endpoint: str
    api_key: str | None = None
    timeout_s: float = 60.0
    client_name: str = "arc-arenaos"
    client_version: str = "1.0"

    _session_id: str | None = field(default=None, init=False, repr=False)
    _id: int = field(default=0, init=False, repr=False)

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _parse(self, payload: dict) -> dict:
        """Extract the JSON-RPC result or raise the real server error."""
        if "error" in payload and payload["error"] is not None:
            err = payload["error"]
            raise MCPError(
                f"MCP server error {err.get('code')}: {err.get('message')}")
        if "result" not in payload:
            raise MCPError(f"malformed JSON-RPC response: {payload}")
        return payload["result"]

    async def _rpc(self, method: str, params: dict | None = None,
                   notify: bool = False) -> dict | None:
        self._id += 1
        body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        # JSON-RPC: a request WITHOUT an id is a NOTIFICATION (server MUST
        # NOT reply). Only true notifications may omit it — requests always
        # carry one, or stateless servers answer 202-with-empty-body.
        if not notify:
            body["id"] = self._id
        if params is not None:
            body["params"] = params
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                res = await client.post(
                    self.endpoint, headers=self._headers(), json=body)
        except httpx.HTTPError as exc:
            raise MCPError(f"transport failure talking to {self.endpoint}: "
                           f"{exc}") from exc
        if res.status_code == 401:
            raise MCPError(
                "authorization required — the API key is missing, invalid, "
                "or expired. Set a valid one and try again.")
        if res.status_code >= 400:
            raise MCPError(
                f"MCP endpoint returned HTTP {res.status_code}: "
                f"{res.text[:300]}")
        sid = res.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        if not res.text.strip():
            if notify:
                return None
            raise MCPError("empty response body from MCP endpoint")
        ctype = res.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            payload = self._read_sse(res.text)
        else:
            try:
                payload = json.loads(res.text)
            except json.JSONDecodeError as exc:
                raise MCPError(
                    f"non-JSON response from MCP endpoint: "
                    f"{res.text[:200]}") from exc
        if notify:
            # servers may reply 202/no body; a JSON echo is also fine
            if isinstance(payload, dict) and "result" not in payload \
                    and "error" not in payload:
                return None
            if isinstance(payload, dict):
                self._parse(payload) if ("result" in payload or "error" in payload) else None
            return None
        if not isinstance(payload, dict):
            raise MCPError(f"unexpected payload type: {type(payload)}")
        return self._parse(payload)

    @staticmethod
    def _read_sse(text: str) -> dict:
        """Parse an SSE body and return the JSON payload of the last
        data event (streamable-http servers emit the response as one)."""
        last_data = ""
        for line in text.splitlines():
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk:
                    last_data = chunk
        if not last_data:
            raise MCPError("SSE stream carried no data payload")
        return json.loads(last_data)

    async def initialize(self) -> dict:
        """Full MCP handshake. Returns the server's initialize result."""
        result = await self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {
                "name": self.client_name,
                "version": self.client_version,
            },
        })
        # required follow-up notification before any tools/* call
        await self._rpc("notifications/initialized", notify=True)
        return result or {}

    async def list_tools(self) -> list[dict]:
        result = await self._rpc("tools/list", {})
        return (result or {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Call a tool; returns the raw MCP content block list."""
        result = await self._rpc("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        if not isinstance(result, dict):
            raise MCPError(f"unexpected tools/call result: {result}")
        if result.get("isError"):
            texts = [c.get("text", "") for c in result.get("content", [])
                     if c.get("type") == "text"]
            raise MCPError(
                f"tool '{name}' returned an error: "
                f"{' '.join(texts)[:600] or result}")
        return result

    async def call_tool_text(self, name: str, arguments: dict | None = None) -> str:
        """Call a tool and flatten its content blocks into readable text."""
        result = await self.call_tool(name, arguments)
        parts: list[str] = []
        for block in result.get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "resource":
                parts.append(json.dumps(block.get("resource", {})))
            else:
                parts.append(json.dumps(block))
        return "\n".join(parts).strip() or "(no content returned)"
