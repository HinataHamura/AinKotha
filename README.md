# AinKotha — আইন কথা

AI-powered Bangla voice/text legal-information and helpline assistant for Bangladesh.

## Run locally
```
cd backend
python -m pip install -r requirements.txt
python validate_dataset.py   # checks laws.json / services.json
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000 in Chrome (Web Speech API needs Chrome/Edge; mic permission required).

Run the automated tests:
```
python -m unittest discover -s tests -v
pytest -q tests/test_classify.py tests/test_backend.py
```

Optional LLM classification (OpenAI-compatible endpoint):
```
set AINKOTHA_LLM_API_KEY=your-server-side-key
set AINKOTHA_LLM_ENDPOINT=https://api.openai.com/v1/chat/completions
set AINKOTHA_LLM_MODEL=gpt-4o-mini
```
Without the key, the deterministic local classifier is used. Never put the key in
frontend code or commit it.

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
- Five deterministic categories: domestic violence, child abuse/child labor, workplace/wage disputes,
  cyber harassment, and general legal aid.
- Optional OpenAI-compatible LLM classification with a safe local keyword fallback.
- Conversation history keeps the previous category for follow-up questions such as “আর কী করতে পারি?”.
- Confidence badge is shown on classified assistant replies.

### Legal information and helplines
- Retrieval-only responses from `backend/data/laws.json` and `backend/data/services.json`;
  the assistant does not invent laws, sections, or phone numbers.
- Call summary shows the detected category, matched laws, and helplines.
- Summary helpline entries expand/collapse to show descriptions and service hours.
- Copy-to-clipboard summary support.
- Dedicated helpline button reads 999, 109, 16430, and 1098 slowly.
- `validate_dataset.py` checks dataset schema and flags unverified law entries.

### Backend and operations
- FastAPI endpoints: `/api/chat`, `/api/tts`, `/api/health`, `/api/config`, and `/api/reload`.
- Anonymous category/latency logging only; transcripts and personal data are not logged.
- Render deployment configuration is provided in the repository root `render.yaml`.

## Known gaps / what a real deployment still needs
- **Legal content is NOT yet verified** — all 6 law entries are marked
  `PLACEHOLDER - needs legal reviewer verification` in `laws.json`. A legal reviewer must
  confirm each law name, section, and summary against bdlaws.gov.bd before this goes live.
- Helpline numbers (999, 109, 16430, 1098, 333) are the real published numbers but should be
  re-confirmed; hours for 16430 need verification.
- LLM classification is optional and retrieval remains deterministic; category accuracy
  still needs a larger labelled test set to certify the SRS target.
- Conversation history is in-memory per session and is lost when the server restarts; there is no
  persistent call-history database yet.
- No admin UI yet for updating laws/services — currently hand-edited JSON + validator script.
- gTTS requires internet access and may be unavailable when Google endpoints are blocked.

## File map
```
backend/
  main.py           FastAPI app, chat/TTS/config/reload endpoints, and anonymous logging
  safety.py         Emergency / self-harm keyword detection (checked first, always)
  classify.py       5-category keyword classifier with Bangla child-labor phrases
  llm.py            Optional OpenAI-compatible classifier adapter
  retrieve.py       Pulls matching laws/services from the verified JSON (no invention)
  responder.py      Builds the short spoken Bangla reply + disclaimer
  validate_dataset.py  Run before deploy to check dataset integrity
  tests/             API, classification, safety, language, fallback, and dataset tests
  data/laws.json, data/services.json   the verified-content dataset (see gaps above)
frontend/
  index.html, style.css, app.js   responsive dark call UI and voice/text interaction
```
