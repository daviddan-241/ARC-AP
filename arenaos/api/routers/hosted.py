"""Reverse proxy for apps self-hosted in ARC's own Linux shell.

An app hosted with the `selfhost` tool (a real process in ARC's own
environment) is reachable from the outside world at:

    https://<arc-url>/hosted/<name>/<anything>

Real proxying via httpx: method, query, headers, and body are forwarded;
the response (including streaming) is returned as-is. Security posture is
honest and narrow:

  * the proxy ONLY forwards to 127.0.0.1 ports registered in the selfhost
    map by the authenticated `selfhost` tool — never an arbitrary host/port
    from the request, so it cannot be turned into an open relay;
  * hop-by-hop headers are stripped both ways;
  * if the process is down or the app was never hosted, the caller gets an
    honest status explaining exactly what to do (selfhost action='restart').
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from arenaos.core.logging import get_logger
from arenaos.hosting import get_entry

logger = get_logger(__name__)

router = APIRouter(prefix="/hosted")

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


@router.api_route("/{name}/{path:path}", methods=METHODS, include_in_schema=False)
@router.api_route("/{name}", methods=METHODS, include_in_schema=False)
async def proxy(name: str, path: str = "", request: Request = None):
    entry = get_entry(name)
    if entry is None:
        return JSONResponse(
            status_code=404,
            content={"detail": (
                f"no app hosted as '{name}'. Host it with the selfhost tool "
                f"(action='host', name='{name}', files/path/command) — it "
                "runs inside ARC's own Linux shell and is served here.")})

    port = entry.get("port")
    upstream = f"http://127.0.0.1:{port}/{path}"

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in HOP_BY_HOP}
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            res = await client.request(
                request.method, upstream,
                params=dict(request.query_params),
                headers=headers, content=body)
    except httpx.ConnectError:
        return JSONResponse(
            status_code=502,
            content={"detail": (
                f"hosted app '{name}' is not responding on port {port} — its "
                "process is down. Restart it with: selfhost action='restart' "
                f"name='{name}' (or check logs: action='logs').")})
    except Exception as exc:
        logger.warning("hosted proxy error for %s: %s", name, exc)
        return JSONResponse(status_code=502, content={
            "detail": f"proxy error reaching '{name}': {exc}"})

    resp_headers = {k: v for k, v in res.headers.items()
                    if k.lower() not in HOP_BY_HOP}
    if res.status_code in (301, 302, 303, 307, 308) and "location" in resp_headers:
        # keep redirects inside the /hosted/<name>/ prefix, not off-site
        loc = resp_headers["location"]
        if loc.startswith("/"):
            resp_headers["location"] = f"/hosted/{name}{loc}"
    return Response(
        content=res.content,
        status_code=res.status_code,
        headers=resp_headers,
    )
