"""FR-3 / NFR-3: Safety detection tests — 100% emergency caught, 0% false positives on normal legal queries."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from safety import check_emergency

# Must detect as emergency
EMERGENCY_CASES = [
    "বাঁচাও, স্বামী ছুরি নিয়ে তাড়া করছে",
    "এখনই মারছে আমাকে",
    "আত্মহত্যা করতে চাই",
    "মরে যেতে ইচ্ছা করে",
    "help me now he has a knife",
    "beating me right now",
    "suicide I want to end my life",
    "want to die",
    "শিশুকে মারছে",
    "জীবন নাশের হুমকি দিয়েছে",
]

# Must NOT detect as emergency (normal legal queries)
NORMAL_CASES = [
    "আমার বেতন দেয় না",
    "ফেসবুকে হয়রানি হচ্ছে",
    "আমার উকিল দরকার",
    "আমি মামলা করতে চাই",
    "salary not paid by employer",
    "I need legal help",
    "my landlord is not returning the deposit",
    "cyber harassment on social media",
]

# Self-harm subset
SELF_HARM_CASES = [
    "আত্মহত্যা করতে চাই",
    "মরে যেতে ইচ্ছা করে",
    "suicide I want to end my life",
    "want to die",
]


def test_all_emergency_cases_detected():
    for text in EMERGENCY_CASES:
        result = check_emergency(text)
        assert result["is_emergency"], f"MISSED emergency: '{text}'"


def test_no_false_positives_on_normal_queries():
    for text in NORMAL_CASES:
        result = check_emergency(text)
        assert not result["is_emergency"], f"FALSE POSITIVE: '{text}'"


def test_self_harm_flagged_correctly():
    for text in SELF_HARM_CASES:
        result = check_emergency(text)
        assert result["is_self_harm"], f"Self-harm not flagged: '{text}'"


def test_non_self_harm_emergency_not_flagged_as_self_harm():
    result = check_emergency("বাঁচাও, স্বামী ছুরি নিয়ে তাড়া করছে")
    assert result["is_emergency"]
    assert not result["is_self_harm"]
