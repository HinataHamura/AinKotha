"""Optional OpenAI-compatible classifier.

Uses curl subprocess instead of urllib to avoid Windows firewall blocking Python's
outbound TCP connections while allowing curl (a known signed binary).
Falls back to None on any failure so the keyword classifier takes over.
"""
import json
import logging
import os
import re
import subprocess

from classify import CATEGORIES

_logger = logging.getLogger("ainkotha.llm")


def classify_with_llm(transcript: str) -> dict | None:
    api_key = os.getenv("AINKOTHA_LLM_API_KEY")
    endpoint = os.getenv("AINKOTHA_LLM_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions")
    model = os.getenv("AINKOTHA_LLM_MODEL", "llama3-8b-8192")
    if not api_key:
        return None

    categories = ", ".join(CATEGORIES)
    prompt = (
        "Classify this transcript into exactly one category. "
        "The transcript may be in Bangla, English, or Banglish (romanized Bangla like 'amar sami amk mare' = my husband hits me, 'betone pay na' = not getting salary, 'meyadottirno ponno' = expired product). "
        f"Categories: {categories}, unknown. "
        "Reply with ONLY a JSON object like: {\"category\": \"workplace_wage\", \"confidence\": 0.9} "
        "No explanation, no markdown, just the JSON. "
        f"Transcript: {transcript}"
    )
    payload = json.dumps({
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    })

    try:
        result = subprocess.run(
            [
                "curl", "-s", "--max-time", "10",
                "-X", "POST", endpoint,
                "-H", f"Authorization: Bearer {api_key}",
                "-H", "Content-Type: application/json",
                "-d", payload,
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            _logger.warning("curl error: %s", result.stderr[:200])
            return None
        data = json.loads(result.stdout)
        content = data["choices"][0]["message"]["content"].strip()
        match = re.search(r'\{[^}]+\}', content, re.DOTALL)
        if not match:
            _logger.warning("LLM returned no JSON: %s", content[:200])
            return None
        parsed = json.loads(match.group())
        category = parsed.get("category", "unknown")
        if category not in CATEGORIES:
            category = "unknown"
        confidence = float(parsed.get("confidence", 0))
        _logger.info("LLM classified '%s' → %s (%.2f)", transcript[:60], category, confidence)
        return {
            "category": category,
            "confidence": max(0.0, min(1.0, confidence)),
            "needs_clarification": category == "unknown" or confidence < 0.65,
        }
    except Exception as exc:
        _logger.warning("LLM call failed: %s", exc)
        return None
