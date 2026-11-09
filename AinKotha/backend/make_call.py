"""Make AinKotha call you (outbound Twilio call). Usage:  python make_call.py [+8801XXXXXXXXX]

Needs in .env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWILIO_TO_NUMBER (or pass it as an
argument) and PUBLIC_BASE_URL (your https ngrok/Render URL). The server must be running and reachable at that URL.
On a Twilio trial account the destination must be a verified number.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"


def load_env() -> None:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    load_env()
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM_NUMBER", "")
    to_number = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TWILIO_TO_NUMBER", "")
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    webhook_key = os.getenv("TWILIO_WEBHOOK_KEY", "").strip()

    missing = [name for name, val in [("TWILIO_ACCOUNT_SID", sid), ("TWILIO_AUTH_TOKEN", token),
                                      ("TWILIO_FROM_NUMBER", from_number), ("TWILIO_TO_NUMBER", to_number),
                                      ("PUBLIC_BASE_URL", base)] if not val]
    if missing:
        print("Missing in .env:", ", ".join(missing))
        return 1
    if not base.startswith("https://"):
        print("PUBLIC_BASE_URL must be an https:// URL (e.g. your ngrok address).")
        return 1

    # Some Windows setups can reach Twilio with Git's curl but not with System32's curl, so try each in turn.
    # Credentials go through curl's stdin config so they never appear in the process list.
    candidates = [c for c in (r"C:\Git\mingw64\bin\curl.exe", r"C:\Program Files\Git\mingw64\bin\curl.exe",
                              shutil.which("curl"), r"C:\Windows\System32\curl.exe") if c and Path(c).exists()]
    data, last_error = None, ""
    attempts = [c for _ in range(3) for c in dict.fromkeys(candidates)]  # up to 3 rounds over the curls
    for curl in attempts:
        result = subprocess.run(
            [curl, "-s", "-S", "-4", "--ssl-no-revoke", "--connect-timeout", "8", "--max-time", "30", "-K", "-", "-X", "POST",
             f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
             "--data-urlencode", f"To={to_number}",
             "--data-urlencode", f"From={from_number}",
             "--data-urlencode", f"Url={base}/twilio/voice" + (f"?key={webhook_key}" if webhook_key else "")],
            input=f'user = "{sid}:{token}"\n', capture_output=True, text=True, encoding="utf-8",
        )
        try:
            data = json.loads(result.stdout)
            break
        except json.JSONDecodeError:
            last_error = f"{curl}: exit {result.returncode} {result.stderr.strip()[:200] or result.stdout[:200]}"
    if data is None:
        print("Could not reach api.twilio.com.", last_error)
        return 1
    if "sid" in data and data.get("status"):
        print(f"Call started ({data['status']}) -> {to_number}. Answer your phone.")
        return 0
    print("Twilio error:", data.get("code"), data.get("message"))
    return 1


if __name__ == "__main__":
    sys.exit(main())
