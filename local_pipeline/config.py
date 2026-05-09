# ============================================================
# config.py  —  Central settings for the data collection pipeline
# Change values here; no other file needs to be touched.
# ============================================================

# How many days back to pull events (applies to all collectors)
DAYS_BACK = 15

# Output file produced by pipeline.py
from pathlib import Path
OUTPUT_FILENAME = Path(__file__).resolve().parent / "output" / "local_activity.csv"

# ── USB duplicate-filter thresholds ─────────────────────────
# Two events of the same category within this many seconds = duplicate
USB_IDENTICAL_WINDOW_SEC = 1.5
# A CONNECT followed by a DISCONNECT within this many seconds = phantom bounce
USB_PHANTOM_BOUNCE_SEC = 1.0

# ── Startup dedup window ─────────────────────────────────────
# LOGON (4624) events fired within this many seconds after a STARTUP
# are service/session-manager noise — they get suppressed.
STARTUP_DEDUP_WINDOW_SEC = 60

# ── Windows Event IDs ────────────────────────────────────────
UMDF_EVENT_IDS = [2003, 2100, 2102]   # 2003=connect, 2100=surprise-remove, 2102=graceful-exit

SECURITY_EVENT_CONFIG = {
    "Security": {
        "ids": [4624, 4800, 4801],
        "labels": {4624: "LOGON", 4800: "LOCK", 4801: "UNLOCK"},
    },
    "System": {
        "ids": [1074, 42, 107, 6005],
        "labels": {
            1074: "LOGOFF(shutdown)",
            42:   "SLEEP",
            107:  "WAKE",
            6005: "LOGON(STARTUP)",
        },
    },
}

# ── USB device regex ─────────────────────────────────────────
# Matches USBSTOR and MTP/Android devices hanging off USB
USB_DEVICE_PATTERN = r"^(USB\\VID_|SWD\\WPDBUSENUM)"

# ── CSV column order ─────────────────────────────────────────
CSV_FIELDNAMES = [
    "timestamp", "source", "event_id",
    "activity", "category",
    "device", "user", "logon_id",
    "browser", "url", "title", "visit_count",
]