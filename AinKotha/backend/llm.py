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
import time

from classify import CATEGORIES

_logger = logging.getLogger("ainkotha.llm")


DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_MODEL = "gemini-flash-lite-latest"


# Gemini is sometimes overloaded (503/429) — try these in order if the primary model fails.
FALLBACK_MODELS = ("gemini-3.1-flash-lite", "gemini-3.5-flash")  # cheapest first
_down_until = 0.0


def _call_model(endpoint: str, api_key: str, model: str, messages: list[dict], timeout: int) -> dict | None:
    body = {"model": model, "temperature": 0.3, "messages": messages}
    if "googleapis.com" in endpoint:
        body["reasoning_effort"] = "low"  # keep voice replies fast
        body["response_format"] = {"type": "json_object"}  # lite models sometimes answer in plain text otherwise
    try:
        result = subprocess.run(
            ["curl", "-s", "--ssl-no-revoke", "--max-time", str(timeout), "-X", "POST", endpoint,
             "-H", f"Authorization: Bearer {api_key}", "-H", "Content-Type: application/json",
             "--data-binary", "@-"],
            input=json.dumps(body), capture_output=True, text=True, encoding="utf-8", timeout=timeout + 5,
        )
        if result.returncode != 0:
            _logger.warning("LLM %s curl error %s: %s", model, result.returncode, result.stderr[:200])
            return None
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or "choices" not in data:
            _logger.warning("LLM %s error response: %s", model, result.stdout[:300].replace(api_key, "<key>"))
            return None
        content = data["choices"][0]["message"]["content"].strip()
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            _logger.warning("LLM %s returned no JSON: %s", model, content[:200])
            return None
        return json.loads(content[start:end + 1])
    except Exception as exc:
        _logger.warning("LLM %s call failed: %s", model, exc)
        return None


def chat_json(messages: list[dict], timeout: int = 12, budget: int = 16) -> dict | None:
    """Send an OpenAI-compatible chat request (via curl) and return the first JSON object in the reply.
    Tries the configured model, then fallbacks, within an overall `budget` of seconds (a phone caller cannot wait).
    Returns None if all fail so callers can fall back."""
    api_key = os.getenv("AINKOTHA_LLM_API_KEY")
    endpoint = os.getenv("AINKOTHA_LLM_ENDPOINT", DEFAULT_ENDPOINT)
    if not api_key:
        return None
    primary = os.getenv("AINKOTHA_LLM_MODEL", DEFAULT_MODEL)
    models = [primary]
    if "googleapis.com" in endpoint:
        models += [m for m in FALLBACK_MODELS if m != primary]
    global _down_until
    if time.time() < _down_until:
        return None
    deadline = time.time() + budget
    for model in models:
        remaining = int(deadline - time.time())
        if remaining < 3:
            break
        parsed = _call_model(endpoint, api_key, model, messages, min(timeout, remaining))
        if parsed is not None:
            return parsed
    _down_until = time.time() + 60  # all models failed: skip the LLM for a minute, use keyword mode
    _logger.warning("All LLM models failed; using keyword mode for 60s")
    return None


AGENT_PROMPT = """You are AinKotha, a warm, calm voice assistant that helps people in Bangladesh understand which kind of legal problem they have and where to get help. You are NOT a lawyer.

Talk like a kind, patient person on a phone call:
- Reply in {lang}. Use simple, short, spoken sentences (max 2-3 sentences, no lists, no markdown, no emojis).
- The user may write Bangla, English or romanized Bangla (Banglish). Understand all of them.
- Show brief empathy, then ask ONE clear question at a time to understand the situation (e.g. who is involved, what exactly happened, how long, whether the person is safe right now, whether they have any proof or documents).
- Do not repeat a question the user already answered. Use everything said earlier in the conversation.
- Never ask for the person's name, address, phone number or other identifying details.

Topics you can help with (category ids): {categories}. Use "unknown" only if the problem is clearly none of these or still unclear.
- domestic_violence: abuse/beating/dowry by husband or family
- child_abuse: abuse, trafficking or labour involving a child
- workplace_wage: unpaid/late wages, wrongful dismissal, factory/office disputes
- cyber_harassment: online threats, leaked photos, hacked accounts, Facebook harassment
- consumer_rights: fake/expired/overpriced goods, cheating by sellers, refused refunds
- legal_aid_general: wants a lawyer, free legal help, or how to file a case

Output ONLY a JSON object, no other text:
{{"reply": "<what you say to the user>", "category": "<category id or unknown>", "ready": <true|false>, "is_emergency": <true|false>, "is_self_harm": <true|false>}}

"is_emergency" is true ONLY for clear, immediate physical danger happening right now, a credible threat to life, or suicidal intent (be conservative: past events and ordinary legal problems are NOT emergencies). "is_self_harm" is true only for suicidal intent or self-harm.

Set "ready": true when you understand the type of problem and have the basic facts (usually after 1-3 questions; do not interrogate). When ready is true, write "reply" as a short, caring 1-2 sentence summary of what you understood and say you will now share the relevant information and helplines. Do NOT include any law names, section numbers, phone numbers or legal advice in "reply": the system adds verified laws and numbers itself.
If you are not ready, "reply" must be your next single question.
This is a spoken call: never say "below", "following" or "see the list"; the system reads the laws and helplines aloud right after your reply.
If the user just greets you or says something off-topic, respond kindly and invite them to describe their problem."""


def converse(history: list[dict], language: str) -> dict | None:
    """Conversational agent turn. history = [{"role": "user"|"bot", "text": ...}] ending with the user's turn.
    Returns {"reply", "category", "ready"} or None if the LLM is unavailable."""
    lang = "English" if language == "en" else "Bangla (Bengali script)"
    messages = [{"role": "system", "content": AGENT_PROMPT.format(lang=lang, categories=", ".join(CATEGORIES))}]
    for turn in history[-8:]:
        messages.append({"role": "user" if turn["role"] == "user" else "assistant", "content": turn["text"]})
    parsed = chat_json(messages)
    if not parsed or not str(parsed.get("reply", "")).strip():
        return None
    category = parsed.get("category", "unknown")
    if category not in CATEGORIES:
        category = "unknown"
    return {
        "reply": str(parsed["reply"]).strip(),
        "category": category,
        "ready": bool(parsed.get("ready")) and category != "unknown",
        "is_emergency": bool(parsed.get("is_emergency")),
        "is_self_harm": bool(parsed.get("is_self_harm")),
    }


def classify_with_llm(transcript: str) -> dict | None:
    categories = ", ".join(CATEGORIES)
    prompt = (
        "Classify this transcript into exactly one category. "
        "The transcript may be in Bangla, English, or Banglish (romanized Bangla like 'amar sami amk mare' = my husband hits me, 'betone pay na' = not getting salary, 'meyadottirno ponno' = expired product). "
        f"Categories: {categories}, unknown. "
        "Reply with ONLY a JSON object like: {\"category\": \"workplace_wage\", \"confidence\": 0.9} "
        "No explanation, no markdown, just the JSON. "
        f"Transcript: {transcript}"
    )
    parsed = chat_json([{"role": "user", "content": prompt}], budget=10)
    if not parsed:
        return None
    try:
        category = parsed.get("category", "unknown")
        if category not in CATEGORIES:
            category = "unknown"
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0))))
    except (TypeError, ValueError):
        return None
    _logger.info("LLM classified '%s' -> %s (%.2f)", transcript[:60], category, confidence)
    return {
        "category": category,
        "confidence": confidence,
        "needs_clarification": category == "unknown" or confidence < 0.65,
    }
