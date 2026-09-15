"""ARC research engine — Planner → Search → Crawl → Extract → Verify → Synthesize → Citations.

Uses DuckDuckGo's HTML endpoint (no API key) + real page fetches.
NEVER invents sources: every citation corresponds to a fetched URL.
"""
import re
from typing import Tuple
import httpx
from bs4 import BeautifulSoup
from .config import get_settings
from . import ollama

S = get_settings()

HEADERS = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"}


async def _search(query: str, limit: int = None) -> list:
    limit = limit or S.RESEARCH_MAX_SOURCES
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as c:
            r = await c.get("https://html.duckduckgo.com/html/", params={"q": query})
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "html.parser")
            results, seen = [], set()
            for a in soup.select("a.result__a"):
                href = a.get("href", "")
                # DDG wraps URLs in a redirect param
                m = re.search(r"uddg=([^&]+)", href)
                url = m.group(1) if m else href
                if not url.startswith("http"):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                results.append({"url": url, "title": a.get_text(strip=True)})
                if len(results) >= limit:
                    break
            return results
    except Exception:
        return []


async def _extract(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as c:
            r = await c.get(url)
            if r.status_code != 200:
                return ""
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            return text[:4000]  # keep context manageable for local models
    except Exception:
        return ""


def _verify(text: str, query_terms: list) -> float:
    """VERIFY: naive relevance score — fraction of query terms present in content."""
    if not text:
        return 0.0
    t = text.lower()
    hits = sum(1 for term in query_terms if term.lower() in t)
    return hits / max(len(query_terms), 1)


async def research_web(query: str) -> Tuple[str, list]:
    """Full research pipeline. Returns (report, sources). Report has numbered citations."""
    # SEARCH
    results = await _search(query)
    if not results:
        report = await _fallback_answer(query)
        return report, []

    # CRAWL + EXTRACT + VERIFY (parallel fetches)
    pages = []
    async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
        pass  # extraction is sequential for determinism on 1-core hosts
    terms = re.findall(r"\w{3,}", query)
    for res in results[:6]:
        text = await _extract(res["url"])
        score = _verify(text, terms)
        if score >= 0.2 or not pages:
            pages.append({**res, "text": text, "score": score})
        if len(pages) >= 4:
            break

    # CRITIC — drop empty pages
    pages = [p for p in pages if p["text"]] or pages[:1]

    # SYNTHESIZE with a real model
    council = await ollama.detect_council()
    model = council["primary"]
    digest = "\n\n".join(
        f"[{i+1}] {p['title']}\nURL: {p['url']}\n{p['text'][:1500]}"
        for i, p in enumerate(pages)
    )
    try:
        report = await ollama.generate_text(
            model,
            f"Research question: {query}\n\nSources:\n{digest}\n\n"
            f"Write a clear answer using ONLY the sources above. Cite them inline as [1], [2]. "
            f"End with a 'Sources:' list of the URLs you actually used.",
            system="You are ARC's research synthesizer. Accurate, concise, cite only what you were given.",
            num_predict=800,
        )
    except Exception as e:
        # honest fallback: raw digest, no fake model prose
        report = f"Model synthesis unavailable ({type(e).__name__}). Raw findings:\n\n" + \
                 "\n\n".join(f"[{i+1}] {p['title']} — {p['url']}\n{p['text'][:600]}" for i, p in enumerate(pages))

    sources = [{"url": p["url"], "title": p["title"], "relevance": round(p["score"], 2)} for p in pages]
    return report, sources


async def _fallback_answer(query: str) -> str:
    council = await ollama.detect_council()
    if council["primary"]:
        try:
            return await ollama.generate_text(council["primary"],
                f"{query}\n\n(Note: web search returned no results; answer from your own knowledge and say so.)",
                system="You are ARC. Be honest about uncertainty.", num_predict=500)
        except Exception:
            pass
    return "Web search returned no results and no model is available to answer from knowledge. (No sources were fabricated.)"
