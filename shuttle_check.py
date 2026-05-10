import os
import json
import uuid
import requests
from datetime import date, timedelta

# Dates to watch (inclusive)
TARGET_DATES = ["2026-07-12", "2026-07-13", "2026-07-14", "2026-07-15"]

# Two people
PARTY_SIZE = 2

# Constants pulled from the HAR
RESOURCE_LOCATION = -2147483642
SHUTTLE_PARENT_MAP = -2147483634
BOOKING_CATEGORY = 9

# Map ID to readable time slot label
TIME_SLOTS = {
    "-2147483017": "4am Alpine Start",
    "-2147483016": "5am Alpine Start",
    "-2147483015": "6:30am-7am",
    "-2147483014": "7am-8am",
    "-2147483013": "8am-9am",
    "-2147483012": "9am-10am",
    "-2147483011": "10am-11am",
    "-2147483010": "11am-12pm",
    "-2147483009": "12pm-1pm",
    "-2147483008": "1pm-2pm",
    "-2147483007": "2pm-3pm",
    "-2147483006": "3pm-4pm",
    "-2147483005": "4pm-5pm",
}

DISCORD_WEBHOOK = os.environ["SHUTTLE_WEBHOOK"]
STATE_FILE = "shuttle_seen.json"
API = "https://reservation.pc.gc.ca/api/availability/map"


def check_date(target):
    """Returns a list of available time slot labels for the given date."""
    next_day = (date.fromisoformat(target) + timedelta(days=1)).isoformat()

    params = {
        "mapId": SHUTTLE_PARENT_MAP,
        "bookingCategoryId": BOOKING_CATEGORY,
        "equipmentCategoryId": "",
        "subEquipmentCategoryId": "",
        "cartUid": str(uuid.uuid4()),
        "cartTransactionUid": str(uuid.uuid4()),
        "bookingUid": str(uuid.uuid4()),
        "groupHoldUid": "",
        "startDate": target,
        "endDate": next_day,
        "getDailyAvailability": "false",
        "isReserving": "true",
        "filterData": "[]",
        "boatLength": 0,
        "boatDraft": 0,
        "boatWidth": 0,
        "peopleCapacityCategoryCounts": json.dumps(
            [{"capacityCategoryId": -32767, "subCapacityCategoryId": None,
              "count": PARTY_SIZE}]
        ),
        "numEquipment": 0,
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/146.0.0.0 Safari/537.36",
        "App-Language": "en-CA",
        "Accept": "application/json, text/plain, */*",
    }

    r = requests.get(API, params=params, headers=headers, timeout=20)

    # Queue-it returns HTML instead of JSON when active
    if "application/json" not in r.headers.get("content-type", ""):
        raise RuntimeError(f"Non-JSON response (likely Queue-it). Status {r.status_code}")

    r.raise_for_status()
    data = r.json()

    # Parent says no availability at all for this day, skip
    if not data.get("mapAvailabilities") or data["mapAvailabilities"][0] != 1:
        return []

    # Walk each time slot map and pick the ones that show available
    available = []
    for map_id, avail_array in data.get("mapLinkAvailabilities", {}).items():
        if avail_array and avail_array[0] == 1:
            label = TIME_SLOTS.get(map_id, f"map {map_id}")
            available.append(label)

    return available


def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_seen(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def send_notification(subject, body):
    r = requests.post(
        DISCORD_WEBHOOK,
        json={"content": f"**{subject}**\n\n{body}"},
        timeout=10,
    )
    r.raise_for_status()


def booking_link(target):
    next_day = (date.fromisoformat(target) + timedelta(days=1)).isoformat()
    return ("https://reservation.pc.gc.ca/create-booking/results"
            f"?transactionLocationId=-2147483647"
            f"&resourceLocationId={RESOURCE_LOCATION}"
            f"&mapId={SHUTTLE_PARENT_MAP}"
            f"&searchTabGroupId=3&bookingCategoryId={BOOKING_CATEGORY}"
            f"&startDate={target}&endDate={next_day}"
            f"&nights=1&isReserving=true"
            f"&peopleCapacityCategoryCounts=%5B%5B-32767,null,{PARTY_SIZE},null%5D%5D")


def main():
    is_first_run = not os.path.exists(STATE_FILE)
    seen = load_seen()
    new_findings = {}
    current_state = {}

    for target in TARGET_DATES:
        try:
            available = check_date(target)
        except Exception as e:
            print(f"Error checking {target}: {e}")
            # Keep prior state for this date so we do not lose it
            current_state[target] = seen.get(target, [])
            continue

        current_state[target] = available
        previous = set(seen.get(target, []))
        truly_new = [s for s in available if s not in previous]
        if truly_new:
            new_findings[target] = truly_new

    save_seen(current_state)

    if is_first_run:
        print(f"First run, recorded current state without notifying")
        return

    if not new_findings:
        print("Nothing new")
        return

    # Build a Discord message
    lines = ["New Moraine Lake shuttle availability:\n"]
    for d in sorted(new_findings):
        slots = ", ".join(new_findings[d])
        lines.append(f"**{d}**: {slots}")
        lines.append(f"<{booking_link(d)}>")
        lines.append("")

    body = "\n".join(lines)
    send_notification(f"Moraine Lake shuttle: {sum(len(v) for v in new_findings.values())} new slot(s)", body)
    print(f"Notified about: {new_findings}")


if __name__ == "__main__":
    main()
