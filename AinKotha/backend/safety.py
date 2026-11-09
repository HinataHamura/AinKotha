"""FR-3: Safety and emergency detection — keyword-first, optional LLM second-pass."""
import json
import logging
import os
import re
from urllib import request as urllib_request

_logger = logging.getLogger("ainkotha.safety")

DANGER_KEYWORDS = [
    # Bangla
    "মেরে ফেলবে", "মেরে ফেলছে", "খুন করবে", "ছুরি নিয়ে", "আগুন লাগিয়ে দিয়েছে",
    "এখনই মারছে", "বাঁচাও", "জীবন নাশের হুমকি", "আত্মহত্যা", "মরে যেতে ইচ্ছা করে",
    "শিশুকে মারছে", "ধর্ষণ করছে", "বিপদে আছি", "সাহায্য করো এখনই",
    "হত্যা করবে", "জীবন শেষ করে দেব", "নিজেকে শেষ করে দিতে চাই",
    # English
    "kill me", "going to kill", "right now he is hitting", "stab", "suicide",
    "want to die", "end my life", "self harm", "beating me right now",
    "help me now", "in danger right now", "he has a knife", "child is being hurt",
    "threatening to kill", "going to hurt", "assault right now",
]

SELF_HARM_KEYWORDS = [
    "আত্মহত্যা", "মরে যেতে ইচ্ছা করে", "বাঁচতে ইচ্ছা করে না",
    "নিজেকে শেষ করে দিতে চাই", "জীবন শেষ করে দেব",
    "suicide", "want to die", "end my life", "self harm", "kill myself",
    "not worth living", "no reason to live",
]

_LLM_SAFETY_PROMPT = (
    "You are a safety classifier. Given a Bangla or English transcript, decide if it contains "
    "signs of IMMEDIATE physical danger, violence happening NOW, credible threat to life, "
    "or suicidal intent. Return JSON only: "
    "{\"is_emergency\": true/false, \"is_self_harm\": true/false, \"reason\": \"one sentence\"}. "
    "Be conservative — only flag clear, immediate danger, not past events or general legal problems. "
    "Transcript: "
)


def _llm_safety_check(transcript: str) -> dict | None:
    """FR-3.1: LLM second-pass for indirect/complex danger signals."""
    import llm
    result = llm.chat_json(
        [{"role": "user", "content": _LLM_SAFETY_PROMPT + transcript}], timeout=8
    )
    if result is None:
        return None
    return {
        "is_emergency": bool(result.get("is_emergency", False)),
        "is_self_harm": bool(result.get("is_self_harm", False)),
    }


def check_emergency(transcript: str, use_llm: bool = True) -> dict:
    """Returns {is_emergency, is_self_harm}.
    Keyword pass first (fast, offline). LLM second-pass only when keyword pass is negative (FR-3.1)."""
    text = transcript.lower()
    is_self_harm_kw = any(k.lower() in text for k in SELF_HARM_KEYWORDS)
    is_emergency_kw = is_self_harm_kw or any(k.lower() in text for k in DANGER_KEYWORDS)

    if is_emergency_kw:
        return {"is_emergency": True, "is_self_harm": is_self_harm_kw}

    # LLM second-pass catches indirect phrasing like "I don't want to see tomorrow"
    llm_result = _llm_safety_check(transcript) if use_llm else None
    if llm_result:
        return llm_result

    return {"is_emergency": False, "is_self_harm": False}
