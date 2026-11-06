"""FR-3: Safety and emergency detection (keyword-based for prototype)."""

DANGER_KEYWORDS = [
    # Bangla
    "মেরে ফেলবে", "মেরে ফেলছে", "খুন করবে", "ছুরি নিয়ে", "আগুন লাগিয়ে দিয়েছে",
    "এখনই মারছে", "বাঁচাও", "জীবন নাশের হুমকি", "আত্মহত্যা", "মরে যেতে ইচ্ছা করে",
    "শিশুকে মারছে", "ধর্ষণ করছে", "বিপদে আছি", "সাহায্য করো এখনই",
    # English
    "kill me", "going to kill", "right now he is hitting", "stab", "suicide",
    "want to die", "end my life", "self harm", "beating me right now",
    "help me now", "in danger right now", "he has a knife", "child is being hurt",
]

SELF_HARM_KEYWORDS = [
    "আত্মহত্যা", "মরে যেতে ইচ্ছা করে", "বাঁচতে ইচ্ছা করে না",
    "suicide", "want to die", "end my life", "self harm", "kill myself",
]


def check_emergency(transcript: str) -> dict:
    """Returns {is_emergency, is_self_harm} per FR-3.1, FR-3.4."""
    text = transcript.lower()
    is_self_harm = any(k.lower() in text for k in SELF_HARM_KEYWORDS)
    is_emergency = is_self_harm or any(k.lower() in text for k in DANGER_KEYWORDS)
    return {"is_emergency": is_emergency, "is_self_harm": is_self_harm}
