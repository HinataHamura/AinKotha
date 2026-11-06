"""FR-5, FR-6: Retrieval-only lookup from the verified dataset. Never invents records."""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

with open(DATA_DIR / "laws.json", encoding="utf-8") as f:
    LAWS = json.load(f)
with open(DATA_DIR / "services.json", encoding="utf-8") as f:
    SERVICES = json.load(f)


def get_laws(category: str, limit: int = 3):
    if category in ("unknown", None):
        return []
    matches = [law for law in LAWS if category in law["categories"]]
    return matches[:limit]


def get_services(category: str, limit: int = 3):
    if category in ("unknown", None):
        # unknown -> still offer general legal aid helpline (FR-4.4)
        matches = [s for s in SERVICES if "legal_aid_general" in s["categories"]]
    else:
        matches = [s for s in SERVICES if category in s["categories"]]
    # Always ensure national legal aid helpline included for legal-nature categories (FR-6.3)
    legal_aid = next((s for s in SERVICES if s["service_id"] == "S3"), None)
    if legal_aid and legal_aid not in matches:
        matches.append(legal_aid)
    return matches[:limit]


def emergency_service():
    return next(s for s in SERVICES if s["service_id"] == "S1")
