"""Phone-call channel via Twilio (voice webhooks -> the same chat() logic the web UI uses).

Flow per call:  /twilio/voice  (greeting + <Gather speech>)
                -> /twilio/gather (caller's words -> chat() -> spoken reply + <Gather> again)
Twilio gives webhooks ~15s, but the LLM + gTTS can take longer, so the reply is built in a worker thread
and, if it is not ready in time, the call is parked on /twilio/wait (silence + <Redirect>) until it is.

Security: every webhook is checked against Twilio's X-Twilio-Signature (HMAC-SHA1 of URL + POST params,
keyed with TWILIO_AUTH_TOKEN). Nothing is accepted if TWILIO_AUTH_TOKEN is not configured.
"""
import asyncio
import base64
import hashlib
import hmac
import logging
import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(prefix="/twilio")
_logger = logging.getLogger("ainkotha.twilio")

GATHER_LANGUAGE = "bn-BD"
WAIT_SECONDS = 3          # answer every webhook quickly (Twilio gave up on 8s); slow replies are parked on /twilio/wait
MAX_WAITS = 12            # ~60s total before apologising
AUDIO_TTL_SECONDS = 300
MAX_SILENT_TURNS = 3

GREETING = ("আমি AinKotha — আইনি তথ্য ও হেল্পলাইন সম্পর্কে সাধারণ তথ্য দিতে পারি। "
            "আমি একজন আইনজীবী নই। আপনার সমস্যা বলুন।")
REPROMPT = "আপনার কথা শুনতে পাইনি। আবার একটু বলবেন?"
GOODBYE = "ধন্যবাদ। প্রয়োজন হলে আবার কল করবেন। আপনি ভালো থাকুন।"
WAITING = "একটু অপেক্ষা করুন, আমি দেখছি।"
SORRY = "দুঃখিত, এখন একটু সমস্যা হচ্ছে। একটু পরে আবার কল করুন। জরুরি বিপদে ৯৯৯ নম্বরে কল করুন।"
GOODBYE_WORDS = ("ধন্যবাদ", "রাখি", "রেখে দিচ্ছি", "বিদায়", "আর কিছু না", "bye", "goodbye")

_pool = ThreadPoolExecutor(max_workers=4)
_audio: dict[str, tuple[float, bytes]] = {}   # audio id -> (created_at, mp3) served to <Play>
_calls: dict[str, dict] = {}                  # CallSid -> {"silent": int, "job": Future|None, "waits": int}


# ---------- security ----------
def _public_base(request: Request) -> str:
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base:
        return base
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}"


def _hook(base: str, path: str) -> str:
    """Webhook URL we hand to Twilio; carries the shared secret (if configured) as ?key=..."""
    key = os.getenv("TWILIO_WEBHOOK_KEY", "").strip()
    return f"{base}/twilio/{path}" + (f"?key={key}" if key else "")


async def _verified_params(request: Request) -> dict:
    """Authenticate a webhook. If Twilio sent X-Twilio-Signature it must be valid (HMAC-SHA1 of URL + params).
    Some paths (e.g. proxies that drop Twilio's headers) arrive unsigned; those must carry our secret ?key=."""
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="Twilio is not configured")
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    signature = request.headers.get("x-twilio-signature", "")
    if signature:
        url = _public_base(request) + request.url.path + (f"?{request.url.query}" if request.url.query else "")
        signed = url + "".join(k + params[k] for k in sorted(params))
        expected = base64.b64encode(hmac.new(token.encode(), signed.encode(), hashlib.sha1).digest()).decode()
        if hmac.compare_digest(expected, signature):
            return params
        _logger.warning("Rejected Twilio webhook: bad signature for %s", request.url.path)
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    key = os.getenv("TWILIO_WEBHOOK_KEY", "").strip()
    if key and hmac.compare_digest(request.query_params.get("key", ""), key):
        return params
    _logger.warning("Rejected Twilio webhook: no signature and no valid key for %s", request.url.path)
    raise HTTPException(status_code=403, detail="Unauthorized")


# ---------- TwiML helpers ----------
def _xml(body: str) -> Response:
    return Response(content=f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>',
                    media_type="application/xml")


def _purge_audio() -> None:
    cutoff = time.time() - AUDIO_TTL_SECONDS
    for key in [k for k, (ts, _) in _audio.items() if ts < cutoff]:
        _audio.pop(key, None)


def _speak_tag(text: str, base: str, audio: bytes | None) -> str:
    """<Play> our gTTS audio (good Bangla); fall back to <Say> if TTS was unavailable."""
    if audio:
        _purge_audio()
        audio_id = uuid.uuid4().hex
        _audio[audio_id] = (time.time(), audio)
        return f"<Play>{base}/twilio/audio/{audio_id}.mp3</Play>"
    return f'<Say language="bn-IN">{escape(text)}</Say>'


def _gather(inner: str, base: str) -> str:
    """Play the prompt first (outside <Gather>, so line noise cannot cut it off), then listen."""
    return (f'{inner}<Gather input="speech" language="{GATHER_LANGUAGE}" speechTimeout="auto" timeout="8" '
            f'actionOnEmptyResult="true" method="POST" action="{escape(_hook(base, "gather"), {chr(34): "&quot;"})}"/>')


def _synth(text: str) -> bytes | None:
    """Blocking synthesis (worker threads only)."""
    import main
    try:
        return main.synthesize(text, "bn")
    except Exception as exc:
        _logger.warning("TTS unavailable for phone reply: %s", exc)
        return None


def _cached(text: str) -> bytes | None:
    import main
    return main.cached_audio(text, "bn")


async def _synth_fast(text: str) -> bytes | None:
    """Audio for a fixed prompt without blocking the event loop or Twilio's ~15s webhook limit.
    Uses the cache if warm; otherwise waits a few seconds (synthesis keeps going in the background)."""
    audio = _cached(text)
    if audio:
        return audio
    fut = asyncio.wrap_future(_pool.submit(_synth, text))
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=7)
    except asyncio.TimeoutError:
        _logger.warning("TTS for fixed prompt not ready in time; using <Say>")
        return None


def warm_up() -> None:
    """Synthesize the fixed prompts in the background at server start."""
    def run():
        for text in (GREETING, REPROMPT, GOODBYE, SORRY, WAITING):
            _synth(text)
        _logger.info("Phone prompts ready")
    threading.Thread(target=run, daemon=True).start()


async def _goodbye(base: str) -> Response:
    return _xml(_speak_tag(GOODBYE, base, await _synth_fast(GOODBYE)) + "<Hangup/>")


def _build_reply(call_sid: str, speech: str) -> dict:
    """Worker thread: run the chatbot, then synthesize its reply."""
    import main
    t0 = time.time()
    resp = main.chat(main.ChatRequest(session_id=f"twilio-{call_sid}", transcript=speech, language="bn"))
    text = resp["reply_text"] if isinstance(resp, dict) else resp.reply_text
    t1 = time.time()
    audio = _synth(text)
    _logger.info("call %s: chat %.1fs + tts %.1fs (%d chars, audio=%s)", call_sid[-6:], t1 - t0, time.time() - t1,
                 len(text), bool(audio))
    return {"text": text, "audio": audio}


async def _await_job(call_sid: str, base: str) -> Response:
    state = _calls[call_sid]
    job: Future = state["job"]
    try:
        # shield: a timeout must not cancel the worker; the next /twilio/wait picks the result up
        result = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(job)), timeout=WAIT_SECONDS)
    except asyncio.TimeoutError:
        state["waits"] += 1
        if state["waits"] > MAX_WAITS:
            state["job"] = None
            _logger.warning("Reply for call %s took too long", call_sid[-6:])
            return _xml(_speak_tag(SORRY, base, _cached(SORRY)) + "<Hangup/>")
        waiting_audio = _cached(WAITING)  # never fall back to <Say> here: just pause if the clip is not ready
        filler = _speak_tag(WAITING, base, waiting_audio) if (state["waits"] == 1 and waiting_audio) else '<Pause length="2"/>'
        return _xml(f'{filler}<Redirect method="POST">{escape(_hook(base, "wait"))}</Redirect>')
    except Exception as exc:
        state["job"] = None
        _logger.warning("Reply for call %s failed: %s", call_sid[-6:], exc)
        return _xml(_speak_tag(SORRY, base, _cached(SORRY)) + "<Hangup/>")
    state["job"] = None
    return _xml(_gather(_speak_tag(result["text"], base, result["audio"]), base))


# ---------- webhooks ----------
@router.post("/voice")
async def voice(request: Request):
    """Incoming (or outgoing, via make_call.py) call starts here."""
    params = await _verified_params(request)
    base = _public_base(request)
    _calls[params.get("CallSid", "unknown")] = {"silent": 0, "job": None, "waits": 0}
    return _xml(_gather(_speak_tag(GREETING, base, await _synth_fast(GREETING)), base))


@router.post("/gather")
async def gather(request: Request):
    _logger.info("gather webhook received")
    params = await _verified_params(request)
    base = _public_base(request)
    call_sid = params.get("CallSid", "unknown")
    state = _calls.setdefault(call_sid, {"silent": 0, "job": None, "waits": 0})
    speech = params.get("SpeechResult", "").strip()

    if not speech:
        state["silent"] += 1
        if state["silent"] >= MAX_SILENT_TURNS:
            _calls.pop(call_sid, None)
            return await _goodbye(base)
        return _xml(_gather(_speak_tag(REPROMPT, base, await _synth_fast(REPROMPT)), base))

    state["silent"] = 0
    if any(word in speech.lower() for word in GOODBYE_WORDS):
        _calls.pop(call_sid, None)
        return await _goodbye(base)

    state["waits"] = 0
    _logger.info("call %s: heard %d chars, building reply", call_sid[-6:], len(speech))
    state["job"] = _pool.submit(_build_reply, call_sid, speech)
    resp = await _await_job(call_sid, base)
    _logger.info("call %s: answered gather webhook", call_sid[-6:])
    return resp


@router.post("/wait")
async def wait(request: Request):
    params = await _verified_params(request)
    call_sid = params.get("CallSid", "unknown")
    if call_sid not in _calls or _calls[call_sid].get("job") is None:
        return _xml(_gather("", _public_base(request)))
    return await _await_job(call_sid, _public_base(request))


@router.get("/audio/{audio_id}.mp3")
def serve_audio(audio_id: str):
    # Twilio does not sign <Play> fetches; the id is an unguessable uuid that expires after AUDIO_TTL_SECONDS.
    entry = _audio.get(audio_id)
    if not entry or time.time() - entry[0] > AUDIO_TTL_SECONDS:
        raise HTTPException(status_code=404)
    return Response(content=entry[1], media_type="audio/mpeg")
