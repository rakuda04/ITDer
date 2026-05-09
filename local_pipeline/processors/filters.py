# ============================================================
# processors/filters.py
#
# Responsibility: take a list of normalized dicts and return
# a cleaned/filtered version.  Pure functions — no I/O.
# ============================================================

import re
from datetime import timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

_USB_PATTERN = re.compile(config.USB_DEVICE_PATTERN, re.IGNORECASE)
_STARTUP_DEDUP_WINDOW = timedelta(seconds=config.STARTUP_DEDUP_WINDOW_SEC)


def filter_usb_only(events: list[dict]) -> list[dict]:
    """
    Keep only UMDF events whose device ID matches a known USB pattern.
    Non-UMDF events pass through untouched.
    """
    result = []
    for entry in events:
        if entry.get("source") != "UMDF":
            result.append(entry)
            continue
        if _USB_PATTERN.search(entry.get("device", "")):
            result.append(entry)
    return result


def filter_usb_duplicates(events: list[dict]) -> list[dict]:
    """
    Remove duplicate UMDF events caused by Windows firing multiple events
    for a single physical connect/disconnect action:

      Condition A — identical category within USB_IDENTICAL_WINDOW_SEC seconds
      Condition B — phantom bounce: CONNECT → DISCONNECT within
                    USB_PHANTOM_BOUNCE_SEC seconds

    Security/Browser events are never touched.
    """
    if not events:
        return []

    # Work on a chronologically sorted copy; don't mutate the input
    sorted_events = sorted(events, key=lambda x: x["timestamp"])

    unique   = []
    last_usb = {}   # device_id → last kept entry

    for entry in sorted_events:
        if entry.get("source") != "UMDF":
            unique.append(entry)
            continue

        # Annotate category (mutating a copy so we don't alter the original)
        entry = {**entry, "category": "CONNECT" if entry["event_id"] == 2003 else "DISCONNECT"}
        dev_id = entry["device"]

        if dev_id in last_usb:
            prev      = last_usb[dev_id]
            time_diff = abs((entry["timestamp"] - prev["timestamp"]).total_seconds())

            # A: duplicate same-category burst
            if entry["category"] == prev["category"] and time_diff <= config.USB_IDENTICAL_WINDOW_SEC:
                continue

            # B: phantom bounce (connect then immediate disconnect)
            if (prev["category"] == "CONNECT"
                    and entry["category"] == "DISCONNECT"
                    and time_diff < config.USB_PHANTOM_BOUNCE_SEC):
                continue

        last_usb[dev_id] = entry
        unique.append(entry)

    return unique


def filter_startup_noise(events: list[dict]) -> list[dict]:
    """
    1. Keep only ONE STARTUP (6005) per boot — drops any dupes within
       STARTUP_DEDUP_WINDOW_SEC (defensive; 6005 normally fires once).
    2. Drop LOGON (4624) events that fire within STARTUP_DEDUP_WINDOW_SEC
       of a STARTUP — those are service/session-manager logons, not the
       interactive user logon.

    All other event types pass through untouched.
    """
    sorted_events = sorted(events, key=lambda x: x["timestamp"])

    last_startup_ts = None
    out = []

    for ev in sorted_events:
        activity = ev.get("activity", "")

        if activity == "STARTUP":
            if (last_startup_ts is None
                    or (ev["timestamp"] - last_startup_ts) > _STARTUP_DEDUP_WINDOW):
                last_startup_ts = ev["timestamp"]
                out.append(ev)
            # else: duplicate 6005 within same boot window → drop
            continue

        if activity == "LOGON" and last_startup_ts is not None:
            if (ev["timestamp"] - last_startup_ts) <= _STARTUP_DEDUP_WINDOW:
                continue  # service/auto logon noise right after boot → drop

        out.append(ev)

    return out