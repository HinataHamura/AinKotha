import base64
import hashlib
import hmac
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
import main
import twilio_voice

TOKEN = "test-token-not-real"
BASE = "https://ainkotha.example"


def signed_post(client, path, params, token=TOKEN):
    data = BASE + path + "".join(k + params[k] for k in sorted(params))
    sig = base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return client.post(path, data=params, headers={"X-Twilio-Signature": sig})


class TwilioVoiceTests(unittest.TestCase):
    def setUp(self):
        main._sessions.clear()
        twilio_voice._calls.clear()
        twilio_voice._audio.clear()
        self.env = patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": TOKEN, "PUBLIC_BASE_URL": BASE,
                                           "AINKOTHA_LLM_API_KEY": ""})
        self.env.start()
        self.tts = patch.object(main, "synthesize", return_value=b"ID3fake-mp3")
        self.tts.start()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.tts.stop()
        self.env.stop()

    def test_bad_signature_rejected(self):
        r = signed_post(self.client, "/twilio/voice", {"CallSid": "CA1"}, token="wrong")
        self.assertEqual(r.status_code, 403)

    def test_unsigned_request_needs_secret_key(self):
        with patch.dict(os.environ, {"TWILIO_WEBHOOK_KEY": "s3cret-key"}):
            self.assertEqual(self.client.post("/twilio/voice", data={"CallSid": "CA1"}).status_code, 403)
            self.assertEqual(self.client.post("/twilio/voice?key=wrong", data={"CallSid": "CA1"}).status_code, 403)
            ok = self.client.post("/twilio/voice?key=s3cret-key", data={"CallSid": "CA1"})
            self.assertEqual(ok.status_code, 200)
            self.assertIn("/twilio/gather?key=s3cret-key", ok.text)  # follow-up webhooks carry the key too

    def test_bad_signature_not_rescued_by_key(self):
        with patch.dict(os.environ, {"TWILIO_WEBHOOK_KEY": "s3cret-key"}):
            data = {"CallSid": "CA1"}
            r = self.client.post("/twilio/voice?key=s3cret-key", data=data, headers={"X-Twilio-Signature": "bogus"})
        self.assertEqual(r.status_code, 403)

    def test_rejected_when_token_not_configured(self):
        with patch.dict(os.environ, {"TWILIO_AUTH_TOKEN": ""}):
            r = self.client.post("/twilio/voice", data={"CallSid": "CA1"})
        self.assertEqual(r.status_code, 503)

    def test_voice_greets_and_gathers_bangla_speech(self):
        r = signed_post(self.client, "/twilio/voice", {"CallSid": "CA1"})
        self.assertEqual(r.status_code, 200)
        self.assertIn('input="speech"', r.text)
        self.assertIn('language="bn-BD"', r.text)
        self.assertIn(f'action="{BASE}/twilio/gather"', r.text)
        self.assertIn(f"<Play>{BASE}/twilio/audio/", r.text)

    def test_gather_answers_and_audio_is_served(self):
        r = signed_post(self.client, "/twilio/gather", {"CallSid": "CA2", "SpeechResult": "আমার মালিক বেতন দেয় না"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("<Gather", r.text)
        audio_id = re.search(r"/twilio/audio/([0-9a-f]+)\.mp3", r.text).group(1)
        audio = self.client.get(f"/twilio/audio/{audio_id}.mp3")
        self.assertEqual(audio.status_code, 200)
        self.assertEqual(audio.content, b"ID3fake-mp3")
        self.assertEqual(self.client.get("/twilio/audio/doesnotexist.mp3").status_code, 404)

    def test_emergency_reply_mentions_999(self):
        r = signed_post(self.client, "/twilio/gather", {"CallSid": "CA3", "SpeechResult": "আমাকে এখনই মেরে ফেলবে"})
        self.assertEqual(r.status_code, 200)
        with patch.object(main, "synthesize", side_effect=RuntimeError("tts down")):
            r = signed_post(self.client, "/twilio/gather", {"CallSid": "CA4", "SpeechResult": "আমাকে এখনই মেরে ফেলবে"})
        self.assertIn("<Say", r.text)  # TTS down -> falls back to <Say>
        self.assertIn("৯৯৯", r.text)

    def test_silence_reprompts_then_hangs_up(self):
        first = signed_post(self.client, "/twilio/gather", {"CallSid": "CA5"})
        self.assertIn("<Gather", first.text)
        second = signed_post(self.client, "/twilio/gather", {"CallSid": "CA5"})
        self.assertNotIn("<Hangup/>", second.text)
        third = signed_post(self.client, "/twilio/gather", {"CallSid": "CA5"})
        self.assertIn("<Hangup/>", third.text)

    def test_goodbye_hangs_up(self):
        r = signed_post(self.client, "/twilio/gather", {"CallSid": "CA6", "SpeechResult": "ধন্যবাদ"})
        self.assertIn("<Hangup/>", r.text)


if __name__ == "__main__":
    unittest.main()
