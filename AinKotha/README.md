# AinKotha — আইন কথা

AI-powered Bangla voice/text legal-information and helpline assistant for Bangladesh.

## Run locally
```
cd backend
python -m pip install -r requirements.txt
python validate_dataset.py   # checks laws.json / services.json
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --env-file .env
```
Open http://localhost:8000 in Chrome (Web Speech API needs Chrome/Edge; mic permission required).

Run the automated tests:
```
python -m unittest discover -s tests -v
pytest -q tests/test_classify.py tests/test_backend.py
```

Optional LLM classification (OpenAI-compatible endpoint):
```
# .env file
AINKOTHA_LLM_API_KEY=your-key
AINKOTHA_LLM_ENDPOINT=https://api.groq.com/openai/v1/chat/completions
AINKOTHA_LLM_MODEL=qwen/qwen3.8-27b
```
Without the key, the deterministic local keyword classifier is used as fallback.
Never put the key in frontend code or commit it.

> **Note on Windows:** Python's `urllib` may be blocked by Windows Firewall/antivirus for
> outbound HTTPS. The LLM module uses `curl` subprocess as transport to work around this.
> Ensure `curl` is available in PATH (Git for Windows includes it).

## Implemented features

### Voice and text interaction
- Consent and disclaimer screen before every call.
- Bangla (`bn-BD`) Web Speech API speech recognition with live transcript.
- gTTS Bangla/English playback through `/api/tts`, with slow mode for phone-number repeats.
- Assistant audio is excluded from speech input with echo filtering; recognition stays available
  during TTS so the user can interrupt a long reply and continue speaking naturally.
- Mute control, text fallback, animated listening/speaking indicator, and configurable silence timeout.
- Language toggle between Bangla and English.

### Safety and conversation
- Emergency detection runs before classification and responds immediately to danger/self-harm phrases.
- Emergency banner with 999 and 109 remains visible throughout an active call.
- Six deterministic categories: domestic violence, child abuse/child labor, workplace/wage disputes,
  cyber harassment, **consumer rights**, and general legal aid.
- Optional OpenAI-compatible LLM classification (Groq Qwen supported) with a safe local keyword fallback.
- **Banglish (romanized Bangla) support** — inputs like "amar sami amk mare" or "beton pay na"
  are classified correctly by both the keyword classifier and the LLM prompt.
- Conversation history keeps the previous category for follow-up questions such as "আর কী করতে পারি?".
- Confidence badge is shown on classified assistant replies.

### Legal information and helplines
- Retrieval-only responses from `backend/data/laws.json` and `backend/data/services.json`;
  the assistant does not invent laws, sections, or phone numbers.
- **Consumer rights** — ভোক্তা অধিকার সংরক্ষণ আইন ২০০৯ (L7) and DNCRP helpline 16121 (S6).
- Call summary shows the detected category, matched laws, and helplines.
- Summary helpline entries expand/collapse to show descriptions and service hours.
- Copy-to-clipboard summary support.
- Dedicated helpline button reads 999, 109, 16430, and 1098 slowly.
- `validate_dataset.py` checks dataset schema and flags unverified law entries.

### Backend and operations
- FastAPI endpoints: `/api/chat`, `/api/tts`, `/api/health`, `/api/config`, and `/api/reload`.
- Anonymous category/latency logging only; transcripts and personal data are not logged.
- Render deployment configuration is provided in the repository root `render.yaml`.

## Categories and helplines

| Category | বাংলা | Key helpline |
|---|---|---|
| `domestic_violence` | পারিবারিক সহিংসতা | 109, 999 |
| `child_abuse` | শিশু নির্যাতন / শিশু শ্রম | 1098, 109 |
| `workplace_wage` | কর্মক্ষেত্র ও মজুরি বিরোধ | 16430 |
| `cyber_harassment` | সাইবার হয়রানি | 999, 16430 |
| `consumer_rights` | ভোক্তা অধিকার | **16121** (DNCRP) |
| `legal_aid_general` | সাধারণ আইনি সহায়তা | 16430 |

## Known gaps / what a real deployment still needs
- **Legal content is NOT yet verified** — all law entries are marked
  `awaiting qualified legal reviewer sign-off` in `laws.json`. A legal reviewer must
  confirm each law name, section, and summary against bdlaws.gov.bd before this goes live.
- Helpline numbers (999, 109, 16430, 1098, 333, 16121) are the real published numbers but should be
  re-confirmed; hours for 16430 and 16121 need verification.
- LLM classification is optional and retrieval remains deterministic; category accuracy
  still needs a larger labelled test set.
- Conversation history is in-memory per session and is lost on server restart.
- No admin UI for updating laws/services — currently hand-edited JSON + validator script.
- gTTS requires internet access and may be unavailable when Google endpoints are blocked.

## File map
```
backend/
  main.py              FastAPI app, chat/TTS/config/reload endpoints, anonymous logging
  safety.py            Emergency / self-harm keyword detection (checked first, always)
  classify.py          6-category keyword classifier — Bangla, English, and Banglish
  llm.py               Optional OpenAI-compatible classifier (curl-based transport)
  retrieve.py          Pulls matching laws/services from verified JSON (no invention)
  responder.py         Builds the short spoken Bangla/English reply + disclaimer
  validate_dataset.py  Run before deploy to check dataset integrity
  tests/               API, classification, safety, language, fallback, and dataset tests
  data/laws.json       7 verified laws (L1–L7) across 6 categories
  data/services.json   6 helplines (S1–S6) including DNCRP 16121
frontend/
  index.html, style.css, app.js   responsive dark call UI and voice/text interaction
```
