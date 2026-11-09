"""FR-7: Response generation — short, simple spoken Bangla, retrieval-only, with disclaimer."""
from classify import CATEGORIES
import retrieve as rt

DISCLAIMER_BN = "এটি সাধারণ তথ্য, আইনি পরামর্শ নয়।"
NOT_LAWYER_BN = "আমি একজন আইনজীবী নই।"
DISCLAIMER_EN = "This is general information, not legal advice."
NOT_LAWYER_EN = "I am not a lawyer."


def build_emergency_reply(is_self_harm: bool) -> dict:
    if is_self_harm:
        text = (
            "আপনার কথা শুনে আমি চিন্তিত। আপনি একা নন। দয়া করে এখনই ৯৯৯ নম্বরে কল করুন অথবা "
            "আপনার কাছের কোনো বিশ্বস্ত মানুষের সাথে কথা বলুন। আপনি কি এখন নিরাপদ জায়গায় আছেন?"
        )
    else:
        text = (
            "আপনি বিপদে আছেন বুঝতে পারছি। এখনই জাতীয় জরুরি সেবা ৯৯৯ নম্বরে কল করুন। "
            "আপনার নিরাপত্তা সবচেয়ে গুরুত্বপূর্ণ।"
        )
    return {
        "reply_text": text,
        "category": "emergency",
        "is_emergency": True,
        "laws": [],
        "services": [rt.emergency_service()],
    }


def build_emergency_reply_en(is_self_harm: bool) -> dict:
    if is_self_harm:
        text = (
            "I am concerned about you. You are not alone. Please call 999 now, "
            "or contact someone you trust and stay with them. Are you safe right now?"
        )
    else:
        text = (
            "If you are in immediate danger, call the national emergency number 999 now. "
            "Your safety is the priority."
        )
    return {
        "reply_text": text,
        "category": "emergency",
        "is_emergency": True,
        "laws": [],
        "services": [rt.emergency_service()],
    }


def build_clarify_reply() -> dict:
    text = "আমি পুরোপুরি বুঝতে পারিনি। আপনি কি একটু বিস্তারিত বলবেন, সমস্যাটি ঠিক কী ধরনের?"
    return {"reply_text": text, "category": "unknown", "is_emergency": False, "laws": [], "services": []}


def build_clarify_reply_en() -> dict:
    text = "I did not fully understand. Could you briefly explain what happened?"
    return {"reply_text": text, "category": "unknown", "is_emergency": False, "laws": [], "services": []}


def build_unknown_reply() -> dict:
    services = rt.get_services("unknown")
    legal_aid = next((x for x in services if x["service_id"] == "S3"), services[0])
    text = (
        "দুঃখিত, এই নির্দিষ্ট বিষয়ে আমার কাছে তথ্য নেই। "
        f"তবে আপনি জাতীয় আইনগত সহায়তা হেল্পলাইন {legal_aid['phone_number']} নম্বরে কল করে সাহায্য পেতে পারেন। "
        + DISCLAIMER_BN
    )
    return {"reply_text": text, "category": "unknown", "is_emergency": False, "laws": [], "services": services}


def build_unknown_reply_en() -> dict:
    services = rt.get_services("unknown")
    legal_aid = next((x for x in services if x["service_id"] == "S3"), services[0])
    text = (
        "I am not sure I have information about this specific issue. "
        f"Please call the National Legal Aid Helpline at {legal_aid['phone_number']}. "
        f"{DISCLAIMER_EN} {NOT_LAWYER_EN}"
    )
    return {"reply_text": text, "category": "unknown", "is_emergency": False, "laws": [], "services": services}


def build_follow_up_reply(category: str) -> dict:
    services = rt.get_services(category)
    guidance = {
        "domestic_violence": "যদি এখন বিপদে থাকেন, নিরাপদ জায়গায় যান এবং ৯৯৯ বা ১০৯-এ যোগাযোগ করুন। সম্ভব হলে বিশ্বস্ত কারও সহায়তা নিন এবং ঘটনার তারিখ ও প্রমাণ নিরাপদে রাখুন।",
        "child_abuse": "শিশুটিকে নিরাপদ জায়গায় রাখুন এবং শিশুর ওপর আরও চাপ বা ক্ষতি হতে দেবেন না। জরুরি বিপদে ৯৯৯, ১০৯ বা ১০৯৮-এ জানান। ঘটনার তথ্য ও প্রমাণ নিরাপদে সংরক্ষণ করুন।",
        "workplace_wage": "বেতন, কাজের সময় ও নিয়োগের প্রমাণ সংরক্ষণ করুন। লিখিতভাবে নিয়োগকর্তার কাছে পাওনা জানান এবং প্রয়োজনে ১৬৪৩০-এ আইনি সহায়তা নিন।",
        "cyber_harassment": "আক্রমণাত্মক বার্তার উত্তর না দিয়ে স্ক্রিনশট, লিংক ও সময় সংরক্ষণ করুন। অ্যাকাউন্ট সুরক্ষিত করুন এবং প্রয়োজনে ৯৯৯ বা ১৬৪৩০-এ যোগাযোগ করুন।",
        "consumer_rights": "পণ্যের রসিদ, মোড়ক বা প্রমাণ সংরক্ষণ করুন। ঘটনার বিবরণ লিখে রাখুন। ১৬১২১ নম্বরে ভোক্তা অধিকার সংরক্ষণ অধিদপ্তরে অভিযোগ করতে পারেন।",
        "legal_aid_general": "ঘটনার সংক্ষিপ্ত বিবরণ ও প্রাসঙ্গিক কাগজপত্র প্রস্তুত করুন। বিনামূল্যে আইনি সহায়তার জন্য ১৬৪৩০-এ যোগাযোগ করতে পারেন।",
    }
    text = guidance.get(category, "ঘটনার তথ্য ও প্রমাণ নিরাপদে সংরক্ষণ করুন এবং প্রয়োজন হলে ১৬৪৩০-এ আইনি সহায়তা নিন।")
    return {
        "reply_text": f"{text} {DISCLAIMER_BN} {NOT_LAWYER_BN}",
        "category": category,
        "is_emergency": False,
        "laws": [],
        "services": services,
    }


def build_follow_up_reply_en(category: str) -> dict:
    services = rt.get_services(category)
    guidance = {
        "domestic_violence": "If you are in danger now, move to a safe place and contact 999 or 109. If possible, ask someone you trust for help and keep a safe record of dates and evidence.",
        "child_abuse": "Keep the child in a safe place and prevent further harm. Report immediate danger to 999, 109, or 1098, and preserve relevant details and evidence safely.",
        "workplace_wage": "Keep records of wages, working hours, and employment. Ask the employer in writing about unpaid wages and contact 16430 for legal help if needed.",
        "cyber_harassment": "Do not engage with the harasser. Save screenshots, links, and timestamps, secure your account, and contact 999 or 16430 if needed.",
        "consumer_rights": "Keep the receipt, packaging, or any evidence of the product or service. Write down the details of what happened. You can file a complaint with the Directorate of National Consumer Rights Protection at 16121.",
        "legal_aid_general": "Prepare a short account of what happened and gather relevant documents. You can contact 16430 for free legal assistance.",
    }
    text = guidance.get(category, "Keep relevant information and evidence safe and contact 16430 for legal assistance if needed.")
    return {
        "reply_text": f"{text} {DISCLAIMER_EN} {NOT_LAWYER_EN}",
        "category": category,
        "is_emergency": False,
        "laws": [],
        "services": services,
    }


def build_reply(category: str, intro: bool = True) -> dict:
    laws = rt.get_laws(category)
    services = rt.get_services(category)
    label_bn = CATEGORIES[category]["label_bn"]

    parts = [f"বুঝতে পেরেছি, এটি {label_bn}-সংক্রান্ত সমস্যা।"] if intro else []
    for law in laws:
        parts.append(f"{law['name_bn']} অনুযায়ী, {law['summary_bn']}")
    if services:
        svc_lines = [f"{s['name_bn']} — {s['phone_number']}" for s in services]
        parts.append("আপনি সাহায্যের জন্য যোগাযোগ করতে পারেন: " + "; ".join(svc_lines) + "।")
    parts.append(DISCLAIMER_BN + " " + NOT_LAWYER_BN + " আর কিছু জানার আছে কি?")

    return {
        "reply_text": " ".join(parts),
        "category": category,
        "is_emergency": False,
        "laws": laws,
        "services": services,
    }


def build_reply_en(category: str, intro: bool = True) -> dict:
    laws = rt.get_laws(category)
    services = rt.get_services(category)
    label_en = CATEGORIES[category]["label_en"]
    parts = [f"I understand this is a {label_en} issue."] if intro else []
    for law in laws:
        parts.append(f"{law['name_en']} says: {law['summary_en']}")
    if services:
        svc_lines = [f"{s['name_en']} — {s['phone_number']}" for s in services]
        parts.append("You can contact: " + "; ".join(svc_lines) + ".")
    parts.append(f"{DISCLAIMER_EN} {NOT_LAWYER_EN} Do you need anything else?")
    return {
        "reply_text": " ".join(parts),
        "category": category,
        "is_emergency": False,
        "laws": laws,
        "services": services,
    }
