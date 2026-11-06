import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
import main
import responder
import validate_dataset


class BackendContractTests(unittest.TestCase):
    def setUp(self):
        main._sessions.clear()
        self.client = TestClient(main.app)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_emergency_is_first_and_structured(self):
        response = self.client.post("/api/chat", json={
            "session_id": "safety-test",
            "transcript": "আমাকে এখনই মেরে ফেলবে",
            "language": "bn",
        })
        body = response.json()
        self.assertTrue(body["is_emergency"])
        self.assertIn("৯৯৯", body["reply_text"])
        self.assertEqual(body["category"], "emergency")

    def test_unknown_gets_at_most_two_clarifications(self):
        payload = {"session_id": "unknown-test", "transcript": "হ্যালো", "language": "bn"}
        first = self.client.post("/api/chat", json=payload).json()
        second = self.client.post("/api/chat", json=payload).json()
        third = self.client.post("/api/chat", json=payload).json()
        self.assertEqual(first["category"], "unknown")
        self.assertEqual(second["category"], "unknown")
        self.assertIn("আইনি", third["reply_text"])

    def test_english_fallback(self):
        response = self.client.post("/api/chat", json={
            "session_id": "english-test",
            "transcript": "my employer has not paid my salary for three months",
            "language": "en",
        })
        body = response.json()
        self.assertEqual(body["category"], "workplace_wage")
        self.assertIn("general information", body["reply_text"])

    def test_child_labor_phrase_is_classified(self):
        body = self.client.post("/api/chat", json={
            "session_id": "child-labor-test",
            "transcript": "বাচ্চা কে দিয়ে কাজ করায়",
            "language": "bn",
        }).json()
        self.assertEqual(body["category"], "child_abuse")
        self.assertGreater(body["confidence"], 0)

    def test_follow_up_uses_previous_category(self):
        session_id = "history-test"
        first = self.client.post("/api/chat", json={
            "session_id": session_id,
            "transcript": "আমার স্বামী মারে",
            "language": "bn",
        }).json()
        follow_up = self.client.post("/api/chat", json={
            "session_id": session_id,
            "transcript": "আর কী করতে পারি?",
            "language": "bn",
        }).json()
        self.assertEqual(first["category"], "domestic_violence")
        self.assertEqual(follow_up["category"], "domestic_violence")
        self.assertNotIn("পুরোপুরি বুঝতে", follow_up["reply_text"])

    def test_llm_result_is_used_when_configured(self):
        with patch("main.llm.classify_with_llm", return_value={
            "category": "cyber_harassment", "confidence": 0.9, "needs_clarification": False
        }):
            body = self.client.post("/api/chat", json={
                "session_id": "llm-test",
                "transcript": "a vague description",
                "language": "bn",
            }).json()
        self.assertEqual(body["category"], "cyber_harassment")


class DatasetTests(unittest.TestCase):
    def test_dataset_schema(self):
        data_dir = Path(__file__).parents[1] / "data"
        laws = json.loads((data_dir / "laws.json").read_text(encoding="utf-8"))
        services = json.loads((data_dir / "services.json").read_text(encoding="utf-8"))
        errors = validate_dataset.validate(laws, validate_dataset.LAW_REQUIRED, "law")
        errors += validate_dataset.validate(services, validate_dataset.SERVICE_REQUIRED, "service")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
