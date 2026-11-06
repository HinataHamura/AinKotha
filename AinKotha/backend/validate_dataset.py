"""FR-10.3: Admin script to validate the dataset before deploy. Run: python validate_dataset.py"""
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

DATA_DIR = Path(__file__).parent / "data"
LAW_REQUIRED = ["law_id", "name_bn", "name_en", "year", "categories", "summary_bn", "summary_en",
                "key_provisions", "source_url", "verified_by", "verified_on"]
SERVICE_REQUIRED = ["service_id", "name_bn", "name_en", "phone_number", "categories",
                    "description_bn", "description_en", "hours", "operator", "source_url", "verified_on"]


def validate(items, required, label):
    errors = []
    ids = set()
    for i, item in enumerate(items):
        for field in required:
            if field not in item or item[field] in (None, ""):
                errors.append(f"{label}[{i}] missing field: {field}")
        idf = "law_id" if label == "law" else "service_id"
        if item.get(idf) in ids:
            errors.append(f"{label}[{i}] duplicate id: {item.get(idf)}")
        ids.add(item.get(idf))
        if label == "service" and not str(item.get("phone_number", "")).replace("-", "").isdigit():
            errors.append(f"{label}[{i}] phone_number not numeric: {item.get('phone_number')}")
        source = str(item.get("source_url", ""))
        if urlparse(source).scheme not in {"http", "https"}:
            errors.append(f"{label}[{i}] source_url must be http(s): {source}")
        try:
            date.fromisoformat(str(item.get("verified_on", "")))
        except ValueError:
            errors.append(f"{label}[{i}] verified_on must be YYYY-MM-DD: {item.get('verified_on')}")
        if not isinstance(item.get("categories"), list) or not item["categories"]:
            errors.append(f"{label}[{i}] categories must be a non-empty list")
    return errors


def main():
    laws = json.loads((DATA_DIR / "laws.json").read_text(encoding="utf-8"))
    services = json.loads((DATA_DIR / "services.json").read_text(encoding="utf-8"))

    errors = validate(laws, LAW_REQUIRED, "law") + validate(services, SERVICE_REQUIRED, "service")

    unreviewed_laws = [l["law_id"] for l in laws if "awaiting" in l.get("verified_by", "").lower()]
    if unreviewed_laws:
        print(f"WARNING: {len(unreviewed_laws)} law(s) awaiting qualified legal-reviewer sign-off: {unreviewed_laws}")

    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print(f"OK — {len(laws)} laws, {len(services)} services, schema valid.")


if __name__ == "__main__":
    main()
