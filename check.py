import os
import json
import requests

# What you are watching for
LOCATION = "costcotire-01248"
SERVICE_IDS = ["oRx5aUP6K3rriXvjR0WV", "8Npus5b4JBG4Xsg4EWNc"]
RESOURCE_IDS = ["JozOBUXIJXgIwnO0wcvA", "aCwRPwlAIR3dqds1sRXA"]

# Date window you care about. Anything outside this gets ignored.
from datetime import date, timedelta
_today = date.today()
TARGET_FROM = _today.isoformat()
TARGET_TO   = (_today + timedelta(days=30)).isoformat()

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

STATE_FILE = "seen.json"
API_BASE = "https://api.waitwhile.com/v2/public/visits"


def get_available_dates():
    """Returns a list like ['2026-05-15', '2026-05-17', ...]"""
    params = [
        ("fromDate", f"{TARGET_FROM}T00:00"),
        ("toDate",   f"{TARGET_TO}T23:59"),
    ]
    for sid in SERVICE_IDS:
        params.append(("serviceIds", sid))
    for rid in RESOURCE_IDS:
        params.append(("resourceIds", rid))

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/146.0.0.0 Safari/537.36",
        "Origin":  "https://waitwhile.com",
        "Referer": "https://waitwhile.com/",
    }

    r = requests.get(
        f"{API_BASE}/{LOCATION}/first-available-dates",
        params=params, headers=headers, timeout=15,
    )
    r.raise_for_status()
    return r.json()


def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(dates):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(dates), f, indent=2)


def send_notification(subject, body):
    r = requests.post(
        DISCORD_WEBHOOK,
        json={"content": f"**{subject}**\n\n{body}"},
        timeout=10,
    )
    r.raise_for_status()


def main():
    is_first_run = not os.path.exists(STATE_FILE)
    available = set(get_available_dates())
    seen = load_seen()

    # Dates inside the window that we have not yet alerted on
    new = sorted(d for d in available
                 if TARGET_FROM <= d <= TARGET_TO and d not in seen)

    if is_first_run:
        # Do not flood the channel on the first run. Just record what is there.
        print(f"First run, recording {len(available)} dates without alerting")
    elif new:
        body = ("New available date(s) at Costco Waterloo Tire Centre:\n\n"
                + "\n".join(f"  - {d}" for d in new)
                + "\n\nBook here: https://tires.costco.ca/Home")
        send_notification(f"Costco tire slot found: {len(new)} new date(s)", body)
        print(f"Notified about {len(new)} new dates: {new}")
    else:
        print("Nothing new")

    # Save what is currently available. If a date drops off and comes back later,
    # you will get a fresh alert.
    save_seen(available)


if __name__ == "__main__":
    send_notification("Test", "Bot is alive and Discord works")
    main()
