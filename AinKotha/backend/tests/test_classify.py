"""NFR-3: Classification accuracy tests — target ≥85% correct category."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from classify import classify

# (transcript, expected_category)
CASES = [
    # domestic_violence
    ("আমার স্বামী আমাকে মারধর করে", "domestic_violence"),
    ("যৌতুকের জন্য আমাকে নির্যাতন করা হচ্ছে", "domestic_violence"),
    ("my husband beats me every night", "domestic_violence"),
    ("domestic violence happening at home", "domestic_violence"),
    # child_abuse
    ("আমার বাচ্চাকে কাজে পাঠানো হচ্ছে, শিশু শ্রম হচ্ছে", "child_abuse"),
    ("child abuse is happening", "child_abuse"),
    # workplace_wage
    ("আমার বেতন দেয় না তিন মাস ধরে", "workplace_wage"),
    ("salary not paid for three months", "workplace_wage"),
    ("আমাকে চাকরি থেকে বের করে দিয়েছে অন্যায়ভাবে", "workplace_wage"),
    ("employer fired me without cause", "workplace_wage"),
    # cyber_harassment
    ("ফেসবুকে আমার ছবি ছড়িয়ে দিয়েছে", "cyber_harassment"),
    ("online harassment on facebook", "cyber_harassment"),
    ("someone hacked my account and posting threats", "cyber_harassment"),
    # legal_aid_general
    ("আমার একজন উকিল দরকার", "legal_aid_general"),
    ("I need legal help to file a case", "legal_aid_general"),
]

# 85% threshold = at least 13 out of 15 correct
THRESHOLD = 0.85


def test_classification_accuracy():
    correct = 0
    failures = []
    for transcript, expected in CASES:
        result = classify(transcript)
        if result["category"] == expected:
            correct += 1
        else:
            failures.append(f"  FAIL: '{transcript[:50]}' → got '{result['category']}', expected '{expected}'")
    accuracy = correct / len(CASES)
    report = f"Accuracy: {correct}/{len(CASES)} = {accuracy:.0%}"
    if failures:
        report += "\nFailures:\n" + "\n".join(failures)
    assert accuracy >= THRESHOLD, f"Classification below {THRESHOLD:.0%} threshold.\n{report}"


def test_unknown_returns_needs_clarification():
    result = classify("hello")
    assert result["category"] == "unknown"
    assert result["needs_clarification"] is True


def test_category_keys_are_valid():
    from classify import CATEGORIES
    valid = set(CATEGORIES.keys()) | {"unknown"}
    for transcript, _ in CASES:
        result = classify(transcript)
        assert result["category"] in valid, f"Invalid category: {result['category']}"
