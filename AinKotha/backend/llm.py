"""Optional OpenAI-compatible classifier.

The local classifier remains the safe fallback. The adapter only returns a
category from the configured allow-list and never supplies legal text.
"""
import json
import os
from urllib import request

from classify import CATEGORIES


def classify_with_llm(transcript: str) -> dict | None:
    api_key = os.getenv("AINKOTHA_LLM_API_KEY")
    endpoint = os.getenv("AINKOTHA_LLM_ENDPOINT", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("AINKOTHA_LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return None

    categories = ", ".join(CATEGORIES)
    prompt = (
        "Classify this Bangla or English legal-help transcript. "
        f"Return JSON only with category and confidence. category must be one of: {categories}, unknown. "
        f"Transcript: {transcript}"
    )
    payload = json.dumps({
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        category = result.get("category", "unknown")
        if category not in CATEGORIES:
            category = "unknown"
        confidence = float(result.get("confidence", 0))
        return {
            "category": category,
            "confidence": max(0.0, min(1.0, confidence)),
            "needs_clarification": category == "unknown" or confidence < 0.65,
        }
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None
