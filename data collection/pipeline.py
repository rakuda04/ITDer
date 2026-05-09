# ============================================================
# pipeline.py  —  Orchestrator
#
# This is the only file that knows about ALL collectors and
# processors.  Run this to produce the final CSV.
#
# To add a new data source:
#   1. Drop a new file in collectors/
#   2. Import it here
#   3. Add it to _collect()
# ============================================================

import csv
import sys
from datetime import datetime
from pathlib import Path
import sys
sys.dont_write_bytecode = True
# Ensure project root is on the path when running directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from collectors.windows_events import get_umdf_events, get_security_events
from collectors.browser_history import get_browser_history
from processors.filters import filter_usb_only, filter_usb_duplicates


# ── collection ───────────────────────────────────────────────

def _collect(days: int) -> list[dict]:
    """
    Call every collector and return their results merged into
    one chronologically sorted list.
    """
    print("[pipeline] Collecting Windows UMDF events...")
    umdf_raw = get_umdf_events(days=days)

    print("[pipeline] Collecting Windows security events...")
    security = get_security_events(days=days)

    print("[pipeline] Collecting browser history...")
    browser = get_browser_history(days=days)

    # ── startup marker (was previously buried in get_security_events) ──
    # Explicit and visible here; easy to remove or reconfigure.
    import os
    startup_marker = {
        "timestamp": datetime.now().astimezone(),
        "source":    "Security",
        "event_id":  4624,
        "activity":  "LOGON (script-run marker)",
        "user":      os.getlogin(),
        "logon_id":  "n/a",
    }

    combined = umdf_raw + security +  [startup_marker] # browser +
    combined.sort(key=lambda x: x["timestamp"])
    return combined


# ── processing ───────────────────────────────────────────────

def _process(events: list[dict]) -> list[dict]:
    """
    Apply filters.  Order matters: filter to USB-only first,
    then deduplicate bursts.
    """
    print("[pipeline] Filtering USB events...")
    usb_only = filter_usb_only(events)
    clean    = filter_usb_duplicates(usb_only)
    return clean


# ── export ───────────────────────────────────────────────────

def _export(events: list[dict], filename: str) -> None:
    if not events:
        print("[pipeline] No events to export.")
        return

    fieldnames = config.CSV_FIELDNAMES

    try:
        with open(filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for entry in events:
                row = {field: entry.get(field, "") for field in fieldnames}
                if isinstance(row["timestamp"], datetime):
                    row["timestamp"] = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S.%f%z")
                writer.writerow(row)
        print(f"[pipeline] ✅ Saved {len(events)} records → {filename}")
    except Exception as exc:
        print(f"[pipeline] Error saving CSV: {exc}")


# ── main ─────────────────────────────────────────────────────

def run(days: int = config.DAYS_BACK, output: str = config.OUTPUT_FILENAME) -> None:
    raw    = _collect(days)
    clean  = _process(raw)
    _export(clean, output)


if __name__ == "__main__":
    run()