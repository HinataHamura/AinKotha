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
    text = (
        "দুঃখিত, এই নির্দিষ্ট বিষয়ে আমার কাছে তথ্য নেই। "
        f"তবে আপনি জাতীয় আইনগত সহায়তা হেল্পলাইন {services[0]['phone_number']} নম্বরে কল করে সাহায্য পেতে পারেন। "
        + DISCLAIMER_BN
    )
    return {"reply_text": text, "category": "unknown", "is_emergency": False, "laws": [], "services": services}


def build_unknown_reply_en() -> dict:
    services = rt.get_services("unknown")
    text = (
        "I am not sure I have information about this specific issue. "
        f"Please call the National Legal Aid Helpline at {services[0]['phone_number']}. "
        f"{DISCLAIMER_EN} {NOT_LAWYER_EN}"
    )
    return {"reply_text": text, "category": "unknown", "is_emergency": False, "laws": [], "services": services}


def build_reply(category: str) -> dict:
    laws = rt.get_laws(category)
    services = rt.get_services(category)
    label_bn = CATEGORIES[category]["label_bn"]

    parts = [f"বুঝতে পেরেছি, এটি {label_bn}-সংক্রান্ত সমস্যা।"]
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


def build_reply_en(category: str) -> dict:
    laws = rt.get_laws(category)
    services = rt.get_services(category)
    label_en = CATEGORIES[category]["label_en"]
    parts = [f"I understand this is a {label_en} issue."]
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
