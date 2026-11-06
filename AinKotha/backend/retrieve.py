"""FR-5, FR-6: Retrieval-only lookup from the verified dataset. Never invents records."""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

with open(DATA_DIR / "laws.json", encoding="utf-8") as f:
    LAWS = json.load(f)
with open(DATA_DIR / "services.json", encoding="utf-8") as f:
    SERVICES = json.load(f)

# FR-6.3: legal aid helpline is always included for any legal-nature category
_LEGAL_AID_ID = "S3"
_NON_LEGAL_CATEGORIES = set()  # all our categories are legal in nature


def get_laws(category: str, limit: int = 3):
    if category in ("unknown", None):
        return []
    matches = [law for law in LAWS if category in law["categories"]]
    return matches[:limit]


def get_services(category: str, limit: int = 3):
    if category in ("unknown", None):
        # FR-4.4: unknown -> offer general legal aid helpline
        matches = [s for s in SERVICES if "legal_aid_general" in s["categories"]]
    else:
        matches = [s for s in SERVICES if category in s["categories"]]

    # FR-6.3: always include the national legal aid helpline for legal-nature problems.
    # Ensure it appears even if the limit would exclude it — place it last if not already present.
    legal_aid = next((s for s in SERVICES if s["service_id"] == _LEGAL_AID_ID), None)
    if legal_aid and legal_aid not in matches:
        # Insert at the end of the capped list (replace last slot if needed to stay within limit)
        if len(matches) < limit:
            matches.append(legal_aid)
        else:
            matches = matches[: limit - 1] + [legal_aid]
    return matches[:limit]


def emergency_service():
    return next(s for s in SERVICES if s["service_id"] == "S1")


def reload_dataset():
    """Reload laws and services from disk without restarting (FR-10, UC-3)."""
    global LAWS, SERVICES
    with open(DATA_DIR / "laws.json", encoding="utf-8") as f:
        LAWS = json.load(f)
    with open(DATA_DIR / "services.json", encoding="utf-8") as f:
        SERVICES = json.load(f)
