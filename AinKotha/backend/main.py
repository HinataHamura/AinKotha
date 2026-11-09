"""AinKotha backend — FastAPI orchestration per SRS section 3 & API contract (15.4).
Channel-independent: this API has no knowledge of voice vs text transport (NFR-10)."""
import time
import json
import logging as _logging
import os
import re
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from gtts import gTTS

import safety
import classify as clf
import responder
import llm
import retrieve as rt

# FR-1.5: configurable silence timeout via env var (seconds)
SILENCE_TIMEOUT_SECONDS = int(os.getenv("AINKOTHA_SILENCE_TIMEOUT", "60"))

APP_DIR = Path(__file__).parent
LOG_FILE = APP_DIR / "data" / "logs.jsonl"

_logging.basicConfig(
    level=_logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

app = FastAPI(title="AinKotha API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_tts_cache: dict[str, bytes] = {}
_tts_domains = ("com", "com.bd", "co.in")
# FR-4.3: session state — clarifications, emergency flag, conversation history
_sessions: dict[str, dict] = {}


class ChatRequest(BaseModel):
    session_id: str
    transcript: str
    language: str = "bn"
    emergency_acknowledged: bool = False


class ChatResponse(BaseModel):
    reply_text: str
    category: str
    is_emergency: bool
    laws: list
    services: list
    confidence: float = 0.0  # dev/demo mode confidence score


class TTSRequest(BaseModel):
    text: str
    language: str = "bn"
    slow: bool = False  # FR-7.3: slow mode for repeating numbers


import logging as _logging
_logger = _logging.getLogger("ainkotha")

_FOLLOW_UP_PHRASES_BN = (
    "আর কী করতে",
    "আর কি করতে",
    "এখন কী কর",
    "এখন কি কর",
    "কী করা উচিত",
    "কি করা উচিত",
    "কী করতে হবে",
    "কি করতে হবে",
)
_FOLLOW_UP_PHRASES_EN = ("what should i do", "what can i do", "what else", "next step")


def _is_follow_up(transcript: str, language: str) -> bool:
    text = transcript.lower()
    phrases = _FOLLOW_UP_PHRASES_EN if language == "en" else _FOLLOW_UP_PHRASES_BN
    return any(phrase in text for phrase in phrases)


def _log(session_id: str, category: str, is_emergency: bool, latency_ms: int):
    # FR-9.1/9.2/9.3: anonymous logs only — no transcript, no personal data
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id_hash": str(hash(session_id) % 10_000_000),
        "category": category,
        "is_emergency": is_emergency,
        "latency_ms": latency_ms,
    }
    line = json.dumps(entry, ensure_ascii=False)
    # Always emit to stdout so Render captures it in its log stream (FR-9.3 workaround for ephemeral disk)
    _logger.info(line)
    # Also try writing to disk (works locally; silently fails on ephemeral Render filesystem)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    start = time.time()
    transcript = (req.transcript or "").strip()
    language = "en" if req.language.lower().startswith("en") else "bn"
    session = _sessions.setdefault(req.session_id, {
        "clarifications": 0,
        "emergency": False,
        "history": [],      # FR-4.3: list of {role, text} for context
        "last_category": None,
        "agent_turns": 0,   # questions asked by the LLM agent since the last answer was delivered
        "delivered": None,  # category whose verified laws/helplines were already shared
    })

    if not transcript:
        resp = {
            "reply_text": (
                "Sorry, I could not hear that. Please repeat."
                if language == "en"
                else "দুঃখিত, আপনার কথা বুঝতে পারিনি। আবার একটু স্পষ্ট করে বলবেন কি?"
            ),
            "category": "unknown",
            "is_emergency": False,
            "laws": [],
            "services": [],
            "confidence": 0.0,
        }
        _log(req.session_id, "unknown", False, int((time.time() - start) * 1000))
        return resp

    # FR-4.3: append user turn to history (keep last 10 turns to avoid token bloat)
    session["history"].append({"role": "user", "text": transcript})
    if len(session["history"]) > 10:
        session["history"] = session["history"][-10:]

    # FR-3: safety first, always
    danger = safety.check_emergency(transcript, use_llm=False)  # keywords only; the agent flags indirect danger below
    agent = None
    if not danger["is_emergency"]:
        agent = llm.converse(session["history"], language)
        if agent and agent["is_emergency"]:
            danger = {"is_emergency": True, "is_self_harm": agent["is_self_harm"]}
        elif not agent:
            danger = safety.check_emergency(transcript)  # LLM unavailable: normal check (also a no-op if it is down)
    if danger["is_emergency"]:
        session["emergency"] = True
        resp = (
            responder.build_emergency_reply_en(danger["is_self_harm"])
            if language == "en"
            else responder.build_emergency_reply(danger["is_self_harm"])
        )
        resp["confidence"] = 1.0
        _log(req.session_id, "emergency", True, int((time.time() - start) * 1000))
        return resp
    if session["emergency"]:
        session["emergency"] = False

    # Conversational LLM agent: chats naturally, asks questions, then hands over to the verified dataset.
    if agent:
        category = agent["category"]
        ready = agent["ready"] or (session["agent_turns"] >= 3 and category != "unknown")
        session["history"].append({"role": "bot", "text": agent["reply"]})
        if not ready:
            session["agent_turns"] += 1
            if category != "unknown":
                session["last_category"] = category
            resp = {"reply_text": agent["reply"], "category": category, "is_emergency": False,
                    "laws": [], "services": [], "confidence": 0.5}
            _log(req.session_id, "clarify", False, int((time.time() - start) * 1000))
            return resp
        # Ready: LLM's short summary + laws/helplines retrieved ONLY from the verified dataset
        session["agent_turns"] = 0
        session["last_category"] = category
        if session["delivered"] == category:
            facts = responder.build_follow_up_reply_en(category) if language == "en" else responder.build_follow_up_reply(category)
        else:
            facts = responder.build_reply_en(category, intro=False) if language == "en" else responder.build_reply(category, intro=False)
            session["delivered"] = category
        facts["reply_text"] = f"{agent['reply']} {facts['reply_text']}"
        facts["confidence"] = 0.9
        _log(req.session_id, category, False, int((time.time() - start) * 1000))
        return facts

    # FR-4: classify — pass history context to LLM for multi-turn awareness
    history_context = " | ".join(t["text"] for t in session["history"][-4:])
    result = llm.classify_with_llm(history_context) or clf.classify(transcript)
    category = result["category"]
    confidence = result.get("confidence", 0.0)
    is_follow_up = bool(session["last_category"] and _is_follow_up(transcript, language))

    # Reuse last known category if clarification is in progress
    needs_clarification = result.get("needs_clarification", False)
    if is_follow_up:
        category = session["last_category"]
        confidence = 0.6
        needs_clarification = False
    elif (category == "unknown" or needs_clarification) and session["last_category"]:
        category = session["last_category"]
        confidence = 0.6
        needs_clarification = False

    if category == "unknown" or needs_clarification:
        count = session["clarifications"]
        if count < 2:
            session["clarifications"] = count + 1
            resp = responder.build_clarify_reply_en() if language == "en" else responder.build_clarify_reply()
        else:
            resp = responder.build_unknown_reply_en() if language == "en" else responder.build_unknown_reply()
        resp["confidence"] = confidence
        _log(req.session_id, "unknown", False, int((time.time() - start) * 1000))
        return resp

    # FR-5/FR-6/FR-7: retrieve + generate
    session["clarifications"] = 0
    session["last_category"] = category
    if is_follow_up:
        resp = (
            responder.build_follow_up_reply_en(category)
            if language == "en"
            else responder.build_follow_up_reply(category)
        )
    else:
        resp = responder.build_reply_en(category) if language == "en" else responder.build_reply(category)
    resp["confidence"] = confidence
    # append bot turn to history
    session["history"].append({"role": "bot", "text": resp["reply_text"][:200]})
    _log(req.session_id, category, False, int((time.time() - start) * 1000))
    return resp


@app.get("/api/services")
def list_services():
    """Verified helplines for the sign-language section (read-only, from services.json)."""
    return rt.SERVICES


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    """Expose safe runtime config to the frontend (FR-1.5)."""
    return {"silence_timeout_seconds": SILENCE_TIMEOUT_SECONDS}


@app.post("/api/reload")
def reload_dataset():
    """UC-3: Reload laws/services JSON without restarting the server."""
    rt.reload_dataset()
    return {"status": "reloaded"}


@app.post("/api/tts")
def text_to_speech(req: TTSRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    if len(text) > 2500:
        raise HTTPException(status_code=400, detail="Text is too long")

    lang = "en" if req.language.lower().startswith("en") else "bn"
    try:
        audio = synthesize(text, lang, req.slow)
    except Exception as exc:
        _logger.warning("TTS failed: %s", exc)
        raise HTTPException(status_code=503, detail="Bangla TTS is temporarily unavailable") from exc
    return StreamingResponse(BytesIO(audio), media_type="audio/mpeg")


def cached_audio(text: str, lang: str = "bn", slow: bool = False) -> bytes | None:
    """Already-synthesized audio, or None (never touches the network)."""
    return _tts_cache.get(f"{lang}:{'slow' if slow else 'normal'}:{text}")


def synthesize(text: str, lang: str = "bn", slow: bool = False) -> bytes:
    """Text -> MP3 bytes (cached). Raises on failure. Shared by /api/tts and the Twilio phone flow."""
    cache_key = f"{lang}:{'slow' if slow else 'normal'}:{text}"
    audio = _tts_cache.get(cache_key)
    if audio is None:
        # gTTS fails when it fetches many pieces in one call, so fetch short pieces separately and join the MP3s.
        # Sequential on purpose: parallel requests get throttled by Google (22s vs ~3s).
        audio = b"".join(_tts_piece(p, lang, slow) for p in _split_for_tts(text))
        _tts_cache[cache_key] = audio
    return audio


def _split_for_tts(text: str, limit: int = 90) -> list[str]:
    """Split on sentence/clause punctuation, then pack pieces up to `limit` characters."""
    parts = [p.strip() for p in re.split(r"(?<=[।.?!;,—])\s+|\s+—\s+", text) if p.strip()]
    pieces: list[str] = []
    for part in parts:
        while len(part) > limit:  # no punctuation: cut at the last space before the limit
            cut = part.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            pieces.append(part[:cut].strip())
            part = part[cut:].strip()
        if pieces and part and len(pieces[-1]) + 1 + len(part) <= limit:
            pieces[-1] += " " + part
        elif part:
            pieces.append(part)
    return pieces or [text]


def _tts_piece(piece: str, lang: str, slow: bool) -> bytes:
    last_error: Exception | None = None
    for domain in _tts_domains * 2:  # Google's TTS stalls at random; short timeout + a second pass over the mirrors
        audio = BytesIO()
        try:
            gTTS(text=piece, lang=lang, tld=domain, slow=slow, timeout=4).write_to_fp(audio)
            return audio.getvalue()
        except Exception as exc:
            last_error = exc
    raise last_error  # type: ignore[misc]


import twilio_voice  # noqa: E402  (phone-call channel; imports `main` lazily to reuse chat()/synthesize())

app.include_router(twilio_voice.router)


@app.on_event("startup")
def _warm_phone_prompts():
    twilio_voice.warm_up()  # pre-build fixed phone prompts so the first call never waits on gTTS

# --- Serve frontend (single process for easy local demo) ---
FRONTEND_DIR = APP_DIR.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
