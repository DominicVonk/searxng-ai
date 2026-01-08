"""
AI Quick Answer Plugin for SearXNG

Provides instant AI-powered answers for simple queries without fetching external URLs.
This is faster than the full summarization plugin and works well for:
- Definitions
- Quick facts
- Simple questions
- Calculations

Trigger: !!ask
Example: "what is quantum computing !!ask"
"""

import os
import re

from searx.plugins import Plugin
from searx.result_types import Answer


# Configuration
TRIGGER = os.getenv("SEARXNG_AI_QUICK_TRIGGER", "!!ask")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
QUICK_ANSWER_TIMEOUT = float(os.getenv("SEARXNG_AI_QUICK_TIMEOUT", "5.0"))


def _strip_trigger(q: str) -> str:
    """Remove the trigger from the query."""
    return q.replace(TRIGGER, "").strip()


def _get_quick_answer(query: str) -> str:
    """
    Get a quick AI answer using only the search snippets.
    
    Args:
        query: User's search query
        
    Returns:
        AI-generated quick answer
    """
    import requests
    
    prompt = f"""Provide a concise, accurate answer to the following question.

Question: {query}

Requirements:
- Keep the answer under 3 paragraphs
- Be factual and precise
- If you're uncertain, say so
- Include key points in bullet format if appropriate
- Do not make up information

Answer:"""

    try:
        r = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that provides accurate, concise answers to questions."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 500,
            },
            timeout=QUICK_ANSWER_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Unable to generate quick answer: {str(e)}"


class SXNGPlugin(Plugin):
    name = "ai_quick_answer"
    description = "Get instant AI answers for simple queries (use !!ask trigger)."
    default_on = False

    def post_search(self, request, search, result_container):
        q = (search.search_query.query or "").strip()
        
        # Check if trigger is present
        if not q or TRIGGER not in q:
            return
        
        # Check if API key is configured
        if not OPENAI_API_KEY:
            return
        
        # Get clean query
        clean_q = _strip_trigger(q)
        
        # Generate quick answer
        try:
            answer_text = _get_quick_answer(clean_q)
            
            # Add answer to results
            result_container.answers.append(
                Answer(
                    answer_type="general",
                    title="AI Quick Answer",
                    content=answer_text
                )
            )
        except Exception:
            # Fail gracefully
            pass
