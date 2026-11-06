"""FR-4: Problem classification into one of 5 categories or Unknown.
Prototype uses keyword scoring (swap for LLM API later per SRS 2.5/13.2)."""

CATEGORIES = {
    "domestic_violence": {
        "label_bn": "পারিবারিক সহিংসতা",
        "label_en": "Domestic violence",
        "keywords": ["স্বামী মারে", "মারধর", "যৌতুক", "নির্যাতন করে", "পারিবারিক সহিংসতা",
                     "husband hits", "beats me", "dowry", "domestic violence", "abuse me"],
    },
    "child_abuse": {
        "label_bn": "শিশু নির্যাতন / শিশু শ্রম",
        "label_en": "Child abuse / child labor",
        "keywords": ["শিশু নির্যাতন", "শিশু শ্রম", "বাচ্চাকে মারে", "বাচ্চাকে কাজে",
                     "বাচ্চা কে দিয়ে কাজ", "বাচ্চাকে দিয়ে কাজ", "শিশুকে দিয়ে কাজ",
                     "শিশু কে দিয়ে কাজ", "শিশুকে কাজে", "শিশু পাচার",
                     "child abuse", "child labor", "my child is", "minor is being"],
    },
    "workplace_wage": {
        "label_bn": "কর্মক্ষেত্র ও মজুরি বিরোধ",
        "label_en": "Workplace and wage dispute",
        "keywords": ["বেতন দেয় না", "বেতন পাচ্ছি না", "বেতন পাই না", "মজুরি বকেয়া", "মজুরি দেয় না",
                     "চাকরি থেকে বের", "কারখানা", "অফিসে সমস্যা", "অফিস থেকে", "কর্মক্ষেত্র",
                     "salary not paid", "wage", "fired", "unpaid", "employer", "factory", "office",
                     "not paying salary", "salary problem", "work dispute"],
    },
    "cyber_harassment": {
        "label_bn": "সাইবার হয়রানি",
        "label_en": "Cyber harassment",
        "keywords": ["ফেসবুকে হয়রানি", "ছবি ছড়িয়ে", "অনলাইনে হুমকি", "হ্যাক",
                     "online harassment", "facebook", "photo leaked", "cyberbully", "online threat", "hacked"],
    },
    "legal_aid_general": {
        "label_bn": "সাধারণ আইনি সহায়তা",
        "label_en": "General legal aid",
        "keywords": ["আইনি সাহায্য", "উকিল", "মামলা করতে", "legal help", "lawyer", "file a case"],
    },
}


def classify(transcript: str) -> dict:
    text = transcript.lower()
    scores = {}
    for cat, info in CATEGORIES.items():
        score = sum(1 for kw in info["keywords"] if kw.lower() in text)
        if score:
            scores[cat] = score
    if not scores:
        return {"category": "unknown", "confidence": 0.0, "needs_clarification": True}
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = scores[best] / total if total else 0.0
    matched_keyword = max(
        (kw for cat in scores for kw in CATEGORIES[cat]["keywords"] if kw.lower() in text),
        key=lambda kw: len(kw.split()),
        default="",
    )
    return {
        "category": best,
        "confidence": round(confidence, 2),
        "needs_clarification": scores[best] <= 1 and len(transcript.split()) < 6
        and len(matched_keyword.split()) < 2,
    }
