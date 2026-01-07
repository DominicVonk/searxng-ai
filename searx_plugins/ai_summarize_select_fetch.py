import os
import re
import json
import asyncio
from typing import List, Tuple, Optional

import httpx
import trafilatura

from searx.plugins import Plugin
from searx.result_types import Answer


# -------------------------
# ENV CONFIG (Coolify vars)
# -------------------------
TRIGGER = os.getenv("SEARXNG_AI_TRIGGER", "!!sum")

# OpenAI-like API
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Limits
RESULTS_FOR_SELECTION = int(os.getenv("SEARXNG_AI_RESULTS_FOR_SELECTION", "40"))  # snippets considered
SELECT_K = int(os.getenv("SEARXNG_AI_SELECT_K", "12"))  # urls LLM returns
FETCH_K = int(os.getenv("SEARXNG_AI_FETCH_K", "7"))    # urls we actually fetch

FETCH_TIMEOUT = float(os.getenv("SEARXNG_AI_FETCH_TIMEOUT", "4.0"))
FETCH_MAX_BYTES = int(os.getenv("SEARXNG_AI_FETCH_MAX_BYTES", "700000"))
EXTRACT_MAX_CHARS = int(os.getenv("SEARXNG_AI_EXTRACT_MAX_CHARS", "9000"))

SELECT_TIMEOUT = float(os.getenv("SEARXNG_AI_SELECT_TIMEOUT", "7.0"))
SUMMARIZE_TIMEOUT = float(os.getenv("SEARXNG_AI_SUMMARIZE_TIMEOUT", "12.0"))

UA = os.getenv("SEARXNG_AI_UA", "Mozilla/5.0 (compatible; SearXNG-AI/1.0)")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")

def _strip_trigger(q: str) -> str:
    return q.replace(TRIGGER, "").strip()


def _openai_chat(prompt: str, timeout: float) -> str:
    # OpenAI-compatible: POST {base}/chat/completions with Bearer key
    import requests
    r = requests.post(
        f"{OPENAI_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": "Follow instructions exactly. Do not invent facts."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def llm_select_urls(query: str, results: list) -> List[str]:
    # Build compact list of (title, snippet, url) from ALL results
    items = []
    for r in results:
        url = getattr(r, "url", "") or ""
        if not _is_http(url):
            continue
        items.append({
            "title": _clean(getattr(r, "title", "") or ""),
            "snippet": _clean(getattr(r, "content", "") or ""),
            "url": url,
        })

    items = items[:RESULTS_FOR_SELECTION]

    prompt = f"""
You are choosing which search results to open to best answer the user.

User query: {query}

Pick up to {SELECT_K} URLs that maximize:
- coverage of different subtopics
- credibility (prefer official/primary sources where relevant)
- non-duplication
- depth (likely to contain substantial info)

Return ONLY valid JSON in this exact shape:
{{
  "urls": ["https://...", "..."]
}}

Search results:
{json.dumps(items, ensure_ascii=False)}
""".strip()

    txt = _openai_chat(prompt, timeout=SELECT_TIMEOUT)

    try:
        data = json.loads(txt)
        urls = [u for u in data.get("urls", []) if isinstance(u, str) and _is_http(u)]
        # dedupe keep order
        seen = set()
        out = []
        for u in urls:
            if u not in seen:
                out.append(u)
                seen.add(u)
        return out
    except Exception:
        return []


async def fetch_and_extract(client: httpx.AsyncClient, url: str) -> Tuple[str, Optional[str]]:
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()

        raw = resp.content[:FETCH_MAX_BYTES].decode(errors="ignore")
        text = trafilatura.extract(raw, include_comments=False, include_tables=False)
        if not text:
            return (url, None)

        text = text.strip()
        if len(text) > EXTRACT_MAX_CHARS:
            text = text[:EXTRACT_MAX_CHARS] + "…"
        return (url, text)
    except Exception:
        return (url, None)


async def fetch_pages(urls: List[str]) -> List[Tuple[str, str]]:
    timeout = httpx.Timeout(FETCH_TIMEOUT, connect=FETCH_TIMEOUT)
    headers = {"User-Agent": UA}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        out = await asyncio.gather(*[fetch_and_extract(client, u) for u in urls])
    return [(u, t) for (u, t) in out if t]


def llm_summarize(query: str, extracted: List[Tuple[str, str]], fallback_results: list) -> str:
    if extracted:
        sources = "\n\n---\n\n".join([f"URL: {u}\nTEXT: {t}" for (u, t) in extracted])
    else:
        # fallback to snippets if fetch blocked
        top = fallback_results[:10]
        sources = "\n".join(
            f"- {getattr(r,'title','')}\n  {getattr(r,'content','')}\n  {getattr(r,'url','')}"
            for r in top
        )

    prompt = f"""
User query: {query}

Output exactly:

SUMMARY:
- (3–7 bullets, factual, cautious)

SUGGESTED LINKS:
1. <url> — <short why>
2. ...

FOLLOW-UP QUERIES:
- (3–7 short searches)

Rules:
- Only cite URLs that appear in SOURCES.
- If evidence is weak or conflicting, say so.
- Do not make up details.

SOURCES:
{sources}
""".strip()

    return _openai_chat(prompt, timeout=SUMMARIZE_TIMEOUT)


class SXNGPlugin(Plugin):
    name = "ai_summarize_select_fetch"
    description = "LLM selects best links from all snippets, fetches/extracts pages, then summarizes."
    default_on = False

    def post_search(self, request, search, result_container):
        q = (search.search_query.query or "").strip()
        if not q or TRIGGER not in q:
            return

        if not OPENAI_API_KEY:
            # Fail closed (don't break search)
            return

        clean_q = _strip_trigger(q)

        # 1) Select URLs using ALL snippets
        selected = llm_select_urls(clean_q, result_container.results)
        if not selected:
            # fallback: use unique hostnames from top results
            selected = []
            seen_hosts = set()
            for r in result_container.results:
                u = getattr(r, "url", "") or ""
                if not _is_http(u):
                    continue
                host = re.sub(r"^https?://", "", u).split("/")[0].lower()
                if host in seen_hosts:
                    continue
                seen_hosts.add(host)
                selected.append(u)
                if len(selected) >= SELECT_K:
                    break

        urls_to_fetch = selected[:FETCH_K]

        # 2) Fetch + extract
        try:
            extracted = asyncio.run(fetch_pages(urls_to_fetch))
            # 3) Summarize + suggested links
            ai_text = llm_summarize(clean_q, extracted, result_container.results)
        except Exception:
            return

        result_container.answers.append(
            Answer(answer_type="general", title="AI summary", content=ai_text)
        )
