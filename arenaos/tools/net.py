"""Network tools: real HTTP requests + keyless web search (DuckDuckGo HTML, parsed)."""
from __future__ import annotations

import re
import urllib.parse
from html import unescape
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from arenaos.core.permissions import Permission
from arenaos.tools.base import BaseTool, ToolContext, ToolResult

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class HttpArgs(BaseModel):
    url: str
    method: str = Field(default="GET", pattern="^(GET|POST|PUT|PATCH|DELETE|HEAD)$")
    headers: Optional[dict[str, str]] = None
    body: Optional[str] = None
    json_body: Optional[dict] = None
    timeout: float = Field(default=30.0, ge=1, le=120)


class HttpRequestTool(BaseTool):
    name = "net.http"
    description = "Perform a real HTTP/REST/GraphQL request and return status + body."
    required_permissions = (Permission.NETWORK_REQUEST,)
    args_model = HttpArgs

    async def execute(self, args: HttpArgs, ctx: ToolContext) -> ToolResult:
        if not args.url.startswith(("http://", "https://")):
            return ToolResult(ok=False, error="url must start with http:// or https://")
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=args.timeout) as client:
                response = await client.request(
                    args.method, args.url, headers=args.headers,
                    content=args.body, json=args.json_body,
                )
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, error=f"request failed: {exc}")
        text = response.text[:12000]
        return ToolResult(ok=200 <= response.status_code < 300,
                          output=ctx.redact(text),
                          error="" if response.status_code < 400 else f"HTTP {response.status_code}",
                          meta={"status_code": response.status_code,
                                "content_type": response.headers.get("content-type", "")})


class SearchArgs(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=10)


_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _ddg_url(href: str) -> str:
    """Unwrap DuckDuckGo redirect links to the real target URL."""
    parsed = urllib.parse.urlparse(href)
    if parsed.path.startswith("/l/"):
        qs = urllib.parse.parse_qs(parsed.query)
        return unescape(qs.get("uddg", [href])[0])
    return href


class WebSearchTool(BaseTool):
    name = "net.search"
    description = "Search the web (DuckDuckGo) and return real parsed results."
    required_permissions = (Permission.NETWORK_REQUEST,)
    args_model = SearchArgs

    async def execute(self, args: SearchArgs, ctx: ToolContext) -> ToolResult:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(args.query)
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0,
                                         headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, error=f"search failed: {exc}")
        if response.status_code != 200:
            return ToolResult(ok=False, error=f"search engine returned HTTP {response.status_code}",
                              meta={"status_code": response.status_code})
        results = []
        for href, title, snippet in _RESULT_RE.findall(response.text):
            clean_title = unescape(_TAG_RE.sub("", title)).strip()
            clean_snippet = unescape(_TAG_RE.sub("", snippet)).strip()
            results.append({"title": clean_title, "url": _ddg_url(href), "snippet": clean_snippet})
            if len(results) >= args.max_results:
                break
        if not results:
            return ToolResult(ok=True, output="(no results parsed for query)",
                              meta={"result_count": 0})
        output = "\n\n".join(f"{r['title']}\n{r['url']}\n{r['snippet']}" for r in results)
        return ToolResult(ok=True, output=ctx.redact(output),
                          meta={"result_count": len(results)})


class DownloadArgs(BaseModel):
    url: str
    path: str  # workspace-relative destination
    max_bytes: int = Field(default=200_000_000, ge=1, le=1_000_000_000)


class DownloadFileTool(BaseTool):
    """Download a URL straight into the workspace jail — the agent's own 'save as'."""

    name = "net.download"
    description = "Download a file from a URL and save it inside the project workspace."
    required_permissions = (Permission.NETWORK_REQUEST, Permission.FILESYSTEM_WRITE)
    args_model = DownloadArgs

    async def execute(self, args: DownloadArgs, ctx: ToolContext) -> ToolResult:
        if not args.url.startswith(("http://", "https://")):
            return ToolResult(ok=False, error="url must start with http:// or https://")
        from pathlib import Path
        root = Path(ctx.workspace).resolve()
        dest = (root / args.path).resolve() if not Path(args.path).is_absolute() else Path(args.path).resolve()
        if dest != root and not str(dest).startswith(str(root) + "/"):
            return ToolResult(ok=False, error=f"path {args.path!r} escapes workspace jail")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            written = 0
            async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
                async with client.stream("GET", args.url, headers={"User-Agent": USER_AGENT}) as response:
                    if response.status_code >= 400:
                        return ToolResult(ok=False, error=f"HTTP {response.status_code}")
                    with open(dest, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            written += len(chunk)
                            if written > args.max_bytes:
                                f.close()
                                dest.unlink(missing_ok=True)
                                return ToolResult(ok=False, error=f"exceeded max_bytes ({args.max_bytes})")
                            f.write(chunk)
            return ToolResult(ok=True, output=f"downloaded {written} bytes to {args.path}",
                              meta={"bytes": written, "files_changed": [args.path]})
        except httpx.HTTPError as exc:
            return ToolResult(ok=False, error=f"download failed: {exc}")
        except OSError as exc:
            return ToolResult(ok=False, error=f"write failed: {exc}")
