"""Optional OpenAI-compatible classifier.

The local classifier remains the safe fallback. The adapter only returns a
category from the configured allow-list and never supplies legal text.
"""
import json
import logging
import os
import re
from urllib import request

from classify import CATEGORIES

_logger = logging.getLogger("ainkotha.llm")


def classify_with_llm(transcript: str) -> dict | None:
    api_key = os.getenv("AINKOTHA_LLM_API_KEY")
    endpoint = os.getenv("AINKOTHA_LLM_ENDPOINT", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("AINKOTHA_LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return None

    categories = ", ".join(CATEGORIES)
    # Ask for JSON inside the reply text — avoids response_format param that Gemini doesn't support
    prompt = (
        "Classify this Bangla or English legal-help transcript into exactly one category. "
        f"Categories: {categories}, unknown. "
        "Reply with ONLY a JSON object like: {\"category\": \"workplace_wage\", \"confidence\": 0.9} "
        "No explanation, no markdown, just the JSON. "
        f"Transcript: {transcript}"
    )
    payload = json.dumps({
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        # Extract JSON even if model wraps it in markdown fences
        match = re.search(r'\{[^}]+\}', content, re.DOTALL)
        if not match:
            _logger.warning("LLM returned no JSON: %s", content[:200])
            return None
        result = json.loads(match.group())
        category = result.get("category", "unknown")
        if category not in CATEGORIES:
            category = "unknown"
        confidence = float(result.get("confidence", 0))
        _logger.info("LLM classified '%s' → %s (%.2f)", transcript[:60], category, confidence)
        return {
            "category": category,
            "confidence": max(0.0, min(1.0, confidence)),
            "needs_clarification": category == "unknown" or confidence < 0.65,
        }
    except Exception as exc:
        _logger.warning("LLM call failed: %s", exc)
        return None
