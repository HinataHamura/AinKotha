"""AinKotha backend — FastAPI orchestration per SRS section 3 & API contract (15.4).
Channel-independent: this API has no knowledge of voice vs text transport (NFR-10)."""
import time
import json
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

APP_DIR = Path(__file__).parent
LOG_FILE = APP_DIR / "data" / "logs.jsonl"

app = FastAPI(title="AinKotha API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# simple in-memory per-session turn counter (for max-2-clarifications rule, FR-4.2)
_session_clarify_count: dict[str, int] = {}
_tts_cache: dict[str, bytes] = {}
_tts_domains = ("com", "com.bd", "co.in")
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


class TTSRequest(BaseModel):
    text: str
    language: str = "bn"


def _log(session_id: str, category: str, is_emergency: bool, latency_ms: int):
    # FR-9.1/9.2/9.3: anonymous logs only — no transcript, no personal data
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id_hash": str(hash(session_id) % 10_000_000),
        "category": category,
        "is_emergency": is_emergency,
        "latency_ms": latency_ms,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    start = time.time()
    transcript = (req.transcript or "").strip()
    language = "en" if req.language.lower().startswith("en") else "bn"
    session = _sessions.setdefault(req.session_id, {"clarifications": 0, "emergency": False})

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
        }
        _log(req.session_id, "unknown", False, int((time.time() - start) * 1000))
        return resp

    # FR-3: safety first, always
    danger = safety.check_emergency(transcript)
    if danger["is_emergency"]:
        session["emergency"] = True
        resp = (
            responder.build_emergency_reply_en(danger["is_self_harm"])
            if language == "en"
            else responder.build_emergency_reply(danger["is_self_harm"])
        )
        _log(req.session_id, "emergency", True, int((time.time() - start) * 1000))
        return resp
    if session["emergency"]:
        session["emergency"] = False

    # FR-4: classify
    result = llm.classify_with_llm(transcript) or clf.classify(transcript)
    category = result["category"]

    if category == "unknown" or result.get("needs_clarification", False):
        count = session["clarifications"]
        if count < 2:
            session["clarifications"] = count + 1
            resp = responder.build_clarify_reply_en() if language == "en" else responder.build_clarify_reply()
        else:
            resp = responder.build_unknown_reply_en() if language == "en" else responder.build_unknown_reply()
        _log(req.session_id, "unknown", False, int((time.time() - start) * 1000))
        return resp

    # FR-5/FR-6/FR-7: retrieve + generate
    session["clarifications"] = 0
    resp = responder.build_reply_en(category) if language == "en" else responder.build_reply(category)
    _log(req.session_id, category, False, int((time.time() - start) * 1000))
    return resp


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/tts")
def text_to_speech(req: TTSRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="Text is too long")

    lang = "en" if req.language.lower().startswith("en") else "bn"
    cache_key = f"{lang}:{text}"
    cached_audio = _tts_cache.get(cache_key)
    if cached_audio is None:
        last_error = None
        for domain in _tts_domains:
            audio = BytesIO()
            try:
                gTTS(text=text, lang=lang, tld=domain, slow=False).write_to_fp(audio)
                cached_audio = audio.getvalue()
                break
            except Exception as exc:
                last_error = exc
        if cached_audio is None:
            raise HTTPException(status_code=503, detail="Bangla TTS is temporarily unavailable") from last_error
        _tts_cache[cache_key] = cached_audio
    return StreamingResponse(BytesIO(cached_audio), media_type="audio/mpeg")


# --- Serve frontend (single process for easy local demo) ---
FRONTEND_DIR = APP_DIR.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
