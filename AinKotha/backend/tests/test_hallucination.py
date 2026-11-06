"""NFR-2: Hallucination tests — system must never cite a law not in the dataset."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import json
import retrieve as rt
from classify import classify
from responder import build_reply, build_reply_en

DATA_DIR = Path(__file__).parent.parent / "data"


def load_dataset_law_ids():
    laws = json.loads((DATA_DIR / "laws.json").read_text(encoding="utf-8"))
    return {law["law_id"] for law in laws}


def load_dataset_service_ids():
    services = json.loads((DATA_DIR / "services.json").read_text(encoding="utf-8"))
    return {s["service_id"] for s in services}


VALID_LAW_IDS = load_dataset_law_ids()
VALID_SERVICE_IDS = load_dataset_service_ids()


def _assert_no_fabrication(resp: dict, label: str):
    for law in resp.get("laws", []):
        assert law["law_id"] in VALID_LAW_IDS, (
            f"[{label}] Fabricated law_id '{law['law_id']}' not in dataset"
        )
    for svc in resp.get("services", []):
        assert svc["service_id"] in VALID_SERVICE_IDS, (
            f"[{label}] Fabricated service_id '{svc['service_id']}' not in dataset"
        )


VALID_CATEGORIES = ["domestic_violence", "child_abuse", "workplace_wage", "cyber_harassment", "legal_aid_general"]


@pytest.mark.parametrize("category", VALID_CATEGORIES)
def test_bn_reply_no_fabrication(category):
    resp = build_reply(category)
    _assert_no_fabrication(resp, f"bn/{category}")


@pytest.mark.parametrize("category", VALID_CATEGORIES)
def test_en_reply_no_fabrication(category):
    resp = build_reply_en(category)
    _assert_no_fabrication(resp, f"en/{category}")


def test_law_count_does_not_exceed_three():
    for category in VALID_CATEGORIES:
        resp = build_reply(category)
        assert len(resp["laws"]) <= 3, f"Too many laws for {category}: {len(resp['laws'])}"


def test_unknown_query_returns_no_fabricated_laws():
    resp = build_reply("legal_aid_general")
    # get_laws for unknown returns []
    laws_for_unknown = rt.get_laws("unknown")
    assert laws_for_unknown == [], "get_laws('unknown') should return empty list"


def test_services_always_include_legal_aid_for_all_categories():
    """FR-6.3: Every legal-nature category response must include S3 (legal aid helpline)."""
    for category in VALID_CATEGORIES:
        services = rt.get_services(category)
        ids = [s["service_id"] for s in services]
        assert "S3" in ids, f"Legal aid helpline (S3) missing from services for category: {category}"


def test_dataset_schema_valid():
    """FR-10.2: Every law record has source_url and verified_on."""
    laws = json.loads((DATA_DIR / "laws.json").read_text(encoding="utf-8"))
    for law in laws:
        assert law.get("source_url"), f"Missing source_url for {law['law_id']}"
        assert law.get("verified_on"), f"Missing verified_on for {law['law_id']}"
