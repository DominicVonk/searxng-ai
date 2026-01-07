import os
import re
import json
import asyncio
from typing import List, Tuple, Optional, Dict
from collections import Counter
from html.parser import HTMLParser

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


# -------------------------
# CONTENT EXTRACTION ENHANCEMENT
# -------------------------

class ContentAnalyzer(HTMLParser):
    """Advanced HTML analyzer for content density and relevance scoring."""
    
    # Tags to exclude (ads, navigation, footers, etc.)
    EXCLUDED_TAGS = {
        'nav', 'header', 'footer', 'aside', 'script', 'style', 'iframe',
        'noscript', 'form', 'button', 'input', 'select', 'textarea'
    }
    
    # Low-value class/id patterns (ads, navigation, social, etc.)
    EXCLUDED_PATTERNS = [
        r'ad[sv]?[-_]',
        r'banner',
        r'promo',
        r'sponsor',
        r'social',
        r'share',
        r'comment',
        r'footer',
        r'header',
        r'nav',
        r'menu',
        r'sidebar',
        r'widget',
        r'popup',
        r'modal',
        r'cookie',
        r'subscribe',
        r'newsletter',
    ]
    
    # High-value tags for main content
    CONTENT_TAGS = {'article', 'main', 'section', 'div', 'p'}
    
    def __init__(self):
        super().__init__()
        self.content_blocks = []
        self.current_block = []
        self.current_tag_stack = []
        self.in_excluded = False
        self.excluded_depth = 0
        
    def handle_starttag(self, tag, attrs):
        self.current_tag_stack.append(tag)
        
        # If already in excluded section, just increase depth for all tags
        if self.in_excluded:
            self.excluded_depth += 1
            return
        
        # Check if we're entering an excluded section
        if tag in self.EXCLUDED_TAGS:
            self.in_excluded = True
            self.excluded_depth = 1
            return
            
        # Check class/id patterns for excluded content
        attrs_dict = dict(attrs)
        for attr_name in ['class', 'id']:
            attr_value = attrs_dict.get(attr_name, '').lower()
            if any(re.search(pattern, attr_value) for pattern in self.EXCLUDED_PATTERNS):
                self.in_excluded = True
                self.excluded_depth = 1
                return
    
    def handle_endtag(self, tag):
        # Remove from stack if it matches (handle malformed HTML gracefully)
        if self.current_tag_stack:
            # Try to find matching tag in stack (handle out-of-order closing)
            try:
                idx = len(self.current_tag_stack) - 1 - list(reversed(self.current_tag_stack)).index(tag)
                self.current_tag_stack.pop(idx)
            except ValueError:
                # Tag not in stack - malformed HTML, continue gracefully
                pass
        
        # Exit excluded section
        if self.in_excluded:
            if self.excluded_depth > 0:
                self.excluded_depth -= 1
            if self.excluded_depth == 0:
                self.in_excluded = False
                
        # Save content block when exiting content tags
        if tag in self.CONTENT_TAGS and self.current_block and not self.in_excluded:
            block_text = ' '.join(self.current_block).strip()
            if len(block_text) > 50:  # Minimum block length
                self.content_blocks.append(block_text)
            self.current_block = []
    
    def handle_data(self, data):
        if not self.in_excluded:
            text = data.strip()
            if text:
                self.current_block.append(text)


def _calculate_content_density(text: str) -> float:
    """Calculate content density score based on various quality metrics."""
    if not text:
        return 0.0
    
    # Length score (prefer substantial content)
    length = len(text)
    length_score = min(length / 5000, 1.0)  # Normalize to max of 5000 chars
    
    # Word density (prefer more words per character - indicates real content)
    # Multiplier of 10 normalizes typical English text (avg ~5 chars/word) to 0.5 range
    WORD_DENSITY_NORMALIZER = 10
    words = text.split()
    word_count = len(words)
    if length == 0:
        word_density = 0
    else:
        word_density = min((word_count / length) * WORD_DENSITY_NORMALIZER, 1.0)
    
    # Sentence structure score (real content has proper sentences)
    # Assume well-written content has ~15 words per sentence on average
    WORDS_PER_SENTENCE = 15
    sentence_endings = text.count('.') + text.count('!') + text.count('?')
    sentence_score = min(sentence_endings / max(word_count / WORDS_PER_SENTENCE, 1), 1.0)
    
    # Alphanumeric ratio (prefer text over symbols/noise)
    alnum_chars = sum(1 for c in text if c.isalnum() or c.isspace())
    alnum_ratio = alnum_chars / length if length > 0 else 0
    
    # Combined score
    density = (
        length_score * 0.3 +
        word_density * 0.25 +
        sentence_score * 0.25 +
        alnum_ratio * 0.2
    )
    
    return density


def _calculate_relevance_score(text: str, query: str) -> float:
    """Calculate relevance score using NLP-inspired techniques."""
    if not text or not query:
        return 0.0
    
    text_lower = text.lower()
    query_lower = query.lower()
    
    # Extract query terms (simple tokenization)
    query_terms = set(re.findall(r'\b\w+\b', query_lower))
    query_terms = {t for t in query_terms if len(t) > 2}  # Filter short words
    
    if not query_terms:
        return 0.0
    
    # Count term frequencies in text
    text_words = re.findall(r'\b\w+\b', text_lower)
    text_word_freq = Counter(text_words)
    
    # Term frequency score
    term_matches = sum(text_word_freq.get(term, 0) for term in query_terms)
    tf_score = min(term_matches / (len(query_terms) * 5), 1.0)
    
    # Exact phrase matching bonus
    phrase_score = 1.0 if query_lower in text_lower else 0.0
    
    # Position score (earlier is better)
    first_match_pos = len(text)
    for term in query_terms:
        pos = text_lower.find(term)
        if pos != -1 and pos < first_match_pos:
            first_match_pos = pos
    
    position_score = 1.0 - (first_match_pos / len(text)) if len(text) > 0 else 0.0
    
    # Combined relevance score
    relevance = (
        tf_score * 0.5 +
        phrase_score * 0.3 +
        position_score * 0.2
    )
    
    return relevance


def _extract_enhanced(html: str, url: str, query: str) -> Optional[str]:
    """
    Enhanced content extraction with advanced heuristics.
    
    Uses multiple strategies:
    1. Content density analysis
    2. Structural filtering (remove ads, nav, footers)
    3. Relevance scoring against query
    4. Trafilatura as fallback
    """
    if not html:
        return None
    
    # Strategy 1: Parse with custom analyzer
    try:
        analyzer = ContentAnalyzer()
        analyzer.feed(html)
        
        if analyzer.content_blocks:
            # Score each block by density and relevance
            scored_blocks = []
            for block in analyzer.content_blocks:
                density = _calculate_content_density(block)
                relevance = _calculate_relevance_score(block, query)
                combined_score = density * 0.4 + relevance * 0.6
                scored_blocks.append((combined_score, block))
            
            # Sort by score and take top blocks
            scored_blocks.sort(reverse=True, key=lambda x: x[0])
            
            # Combine top blocks up to character limit
            extracted = []
            total_chars = 0
            for score, block in scored_blocks:
                if score < 0.1:  # Minimum quality threshold
                    break
                if total_chars + len(block) > EXTRACT_MAX_CHARS:
                    remaining = EXTRACT_MAX_CHARS - total_chars
                    if remaining > 200:  # Only add if substantial space left
                        extracted.append(block[:remaining])
                    break
                extracted.append(block)
                total_chars += len(block)
            
            if extracted:
                result = '\n\n'.join(extracted)
                if len(result) > 100:  # Minimum viable content
                    return result
    except (ValueError, TypeError) as e:
        # Expected errors from HTML parsing - fall through to trafilatura
        pass
    
    # Strategy 2: Fallback to trafilatura with enhanced config
    try:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,  # Tables can contain useful data
            no_fallback=False,
            favor_precision=True,  # Prefer quality over quantity
            favor_recall=False,
        )
        
        if text:
            # Apply relevance filtering to trafilatura output
            paragraphs = text.split('\n\n')
            scored_paragraphs = []
            
            for para in paragraphs:
                if len(para.strip()) < 50:
                    continue
                density = _calculate_content_density(para)
                relevance = _calculate_relevance_score(para, query)
                combined_score = density * 0.4 + relevance * 0.6
                scored_paragraphs.append((combined_score, para))
            
            if scored_paragraphs:
                scored_paragraphs.sort(reverse=True, key=lambda x: x[0])
                
                # Combine top paragraphs
                result_parts = []
                total_chars = 0
                for score, para in scored_paragraphs:
                    if score < 0.05:
                        break
                    if total_chars + len(para) > EXTRACT_MAX_CHARS:
                        remaining = EXTRACT_MAX_CHARS - total_chars
                        if remaining > 200:
                            result_parts.append(para[:remaining] + "…")
                        break
                    result_parts.append(para)
                    total_chars += len(para)
                
                if result_parts:
                    return '\n\n'.join(result_parts)
        
        # Last resort: return raw trafilatura output
        if text and len(text.strip()) > 100:
            return text[:EXTRACT_MAX_CHARS]
            
    except (ValueError, TypeError) as e:
        # Expected errors from trafilatura parsing
        pass
    
    return None


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


async def fetch_and_extract(client: httpx.AsyncClient, url: str, query: str) -> Tuple[str, Optional[str]]:
    """
    Fetch and extract content from a URL with enhanced extraction.
    
    Args:
        client: HTTP client
        url: URL to fetch
        query: User query for relevance scoring
        
    Returns:
        Tuple of (url, extracted_text or None)
    """
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()

        raw = resp.content[:FETCH_MAX_BYTES].decode(errors="ignore")
        
        # Use enhanced extraction with query-aware relevance
        text = _extract_enhanced(raw, url, query)
        
        if not text:
            return (url, None)

        text = text.strip()
        if len(text) > EXTRACT_MAX_CHARS:
            text = text[:EXTRACT_MAX_CHARS] + "…"
        return (url, text)
    except Exception:
        return (url, None)


async def fetch_pages(urls: List[str], query: str) -> List[Tuple[str, str]]:
    """
    Fetch and extract content from multiple URLs in parallel.
    
    Args:
        urls: List of URLs to fetch
        query: User query for relevance scoring
        
    Returns:
        List of (url, extracted_text) tuples for successful extractions
    """
    timeout = httpx.Timeout(FETCH_TIMEOUT, connect=FETCH_TIMEOUT)
    headers = {"User-Agent": UA}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        out = await asyncio.gather(*[fetch_and_extract(client, u, query) for u in urls])
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
            extracted = asyncio.run(fetch_pages(urls_to_fetch, clean_q))
            # 3) Summarize + suggested links
            ai_text = llm_summarize(clean_q, extracted, result_container.results)
        except Exception:
            return

        result_container.answers.append(
            Answer(answer_type="general", title="AI summary", content=ai_text)
        )
