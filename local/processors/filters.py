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
import local.config as config

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


# SYSTEM account logon IDs — never real user activity
_SYSTEM_LOGON_IDS = {"0x3e7", "0x3e4", "0x3e5", "0x3e3"}

def filter_startup_noise(events: list[dict]) -> list[dict]:
    """
    1. Drop any LOGON with a SYSTEM account logon_id (0x3e7, 0x3e4, etc.)
       — these are service/session-manager logons, never real user activity.
    2. Keep only ONE STARTUP (6005) per boot.
    3. Drop LOGON events within STARTUP_DEDUP_WINDOW_SEC before OR after
       a STARTUP event.

    All other event types pass through untouched.
    """
    sorted_events = sorted(events, key=lambda x: x["timestamp"])

    # Pass 1 — collect all STARTUP timestamps
    startup_times = [
        ev["timestamp"] for ev in sorted_events
        if ev.get("activity") == "STARTUP"
    ]

    # Pass 2 — filter
    seen_startups = set()
    out = []

    for ev in sorted_events:
        activity = ev.get("activity", "")

        # Drop SYSTEM account logons entirely
        if activity == "LOGON":
            logon_id = str(ev.get("logon_id", "")).lower()
            if logon_id in _SYSTEM_LOGON_IDS:
                continue

        if activity == "STARTUP":
            ts_key = ev["timestamp"].replace(microsecond=0)
            if ts_key not in seen_startups:
                seen_startups.add(ts_key)
                out.append(ev)
            continue

        # Drop LOGONs within window of any startup (before OR after)
        if activity == "LOGON":
            near_startup = any(
                abs((ev["timestamp"] - st).total_seconds()) <= _STARTUP_DEDUP_WINDOW.total_seconds()
                for st in startup_times
            )
            if near_startup:
                continue

        out.append(ev)

    return out

def filter_fake_sleep(events: list[dict]) -> list[dict]:
    """
    Drop SLEEP/WAKE pairs that are closer than SLEEP_WAKE_MIN_SEC apart.
    These are fake sleep cycles from display timeout or USB power management,
    not real user sleep. Both the SLEEP and its matching WAKE are dropped.
    """
    sorted_events = sorted(events, key=lambda x: x["timestamp"])
    min_sec = config.SLEEP_WAKE_MIN_SEC

    # Find indices of fake sleep/wake pairs to drop
    drop = set()
    pending_sleep_idx = None

    for i, ev in enumerate(sorted_events):
        activity = ev.get("activity", "")
        if activity == "SLEEP":
            pending_sleep_idx = i
        elif activity == "WAKE" and pending_sleep_idx is not None:
            diff = (ev["timestamp"] - sorted_events[pending_sleep_idx]["timestamp"]).total_seconds()
            if diff < min_sec:
                drop.add(pending_sleep_idx)
                drop.add(i)
            pending_sleep_idx = None

    return [ev for i, ev in enumerate(sorted_events) if i not in drop]
