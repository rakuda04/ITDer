# ============================================================
# collectors/browser_history.py
# ============================================================

import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


# ── timestamp helpers ────────────────────────────────────────

def _webkit_to_dt(webkit_ts: int) -> datetime:
    """Chrome/Edge/Brave: microseconds since 1601-01-01 UTC."""
    if not webkit_ts:
        return datetime.now().astimezone()
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    return (epoch + timedelta(microseconds=webkit_ts)).astimezone()


def _prtime_to_dt(prtime_us: int) -> datetime:
    """Firefox: microseconds since Unix epoch."""
    if not prtime_us:
        return datetime.now().astimezone()
    return datetime.fromtimestamp(prtime_us / 1_000_000, tz=timezone.utc).astimezone()


# ── safe copy (handles locked DB while browser is open) ──────

def _safe_copy(src: Path) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    shutil.copy2(src, tmp.name)
    return tmp.name


# ── known browser paths per OS ───────────────────────────────

def _get_browser_paths() -> dict[str, list[Path]]:
    home = Path.home()

     # Windows
    local   = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
    roaming = Path(os.environ.get("APPDATA",      home / "AppData/Roaming"))
    return {
        "Chrome":  [local   / "Google/Chrome/User Data/Default/History"],
        "Edge":    [local   / "Microsoft/Edge/User Data/Default/History"],
        "Brave":   [local   / "BraveSoftware/Brave-Browser/User Data/Default/History"],
        "Opera":   [roaming / "Opera Software/Opera Stable/History"],
        "Vivaldi": [local   / "Vivaldi/User Data/Default/History"],
        "Firefox": [
            *(roaming / "Mozilla/Firefox/Profiles").glob("*.default*/places.sqlite"),
            *(roaming / "Mozilla/Firefox/Profiles").glob("*.default-release*/places.sqlite"),
        ],
    }




# ── per-browser query functions ──────────────────────────────

def _query_chromium(db_path: Path, browser_name: str, days: int) -> list[dict]:
    results = []
    tmp = _safe_copy(db_path)
    try:
        now_webkit = int(
            (datetime.now(timezone.utc) - datetime(1601, 1, 1, tzinfo=timezone.utc))
            .total_seconds() * 1_000_000
        )
        cutoff_webkit = days * 86_400 * 1_000_000  # days → microseconds

        conn = sqlite3.connect(tmp)
        cur  = conn.cursor()
        cur.execute("""
            SELECT url, title, visit_count, last_visit_time
            FROM urls
            WHERE last_visit_time > 0
            ORDER BY last_visit_time DESC
        """)
        for url, title, visit_count, ts in cur.fetchall():
            if (now_webkit - ts) > cutoff_webkit:
                continue
            results.append({
                "timestamp":   _webkit_to_dt(ts),
                "source":      "Browser",
                "event_id":    None,
                "browser":     browser_name,
                "url":         url,
                "title":       title or "",
                "visit_count": visit_count,
                "user":        os.getlogin(),
            })
        conn.close()
    except Exception as exc:
        print(f"[browser_history] Error reading {browser_name} ({db_path}): {exc}")
    finally:
        os.unlink(tmp)
    return results


def _query_firefox(db_path: Path, days: int) -> list[dict]:
    results = []
    tmp = _safe_copy(db_path)
    try:
        now_us    = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        cutoff_us = days * 86_400 * 1_000_000

        conn = sqlite3.connect(tmp)
        cur  = conn.cursor()
        cur.execute("""
            SELECT url, title, visit_count, last_visit_date
            FROM moz_places
            WHERE visit_count > 0
            ORDER BY last_visit_date DESC
        """)
        for url, title, visit_count, ts in cur.fetchall():
            if ts and (now_us - ts) > cutoff_us:
                continue
            results.append({
                "timestamp":   _prtime_to_dt(ts),
                "source":      "Browser",
                "event_id":    None,
                "browser":     "Firefox",
                "url":         url,
                "title":       title or "",
                "visit_count": visit_count,
                "user":        os.getlogin(),
            })
        conn.close()
    except Exception as exc:
        print(f"[browser_history] Error reading Firefox ({db_path}): {exc}")
    finally:
        os.unlink(tmp)
    return results


# ── public collector ─────────────────────────────────────────

def get_browser_history(days: int = config.DAYS_BACK) -> list[dict]:
    """
    Scan all known browser locations, collect history for the past `days` days.
    Returns a flat list of dicts sorted oldest-first.
    """
    all_results = []
    browser_paths = _get_browser_paths()

    for browser, paths in browser_paths.items():
        for db_path in paths:
            if not Path(db_path).exists():
                continue
            print(f"[browser_history] Found {browser}: {db_path}")
            rows = _query_firefox(db_path, days) if browser == "Firefox" else _query_chromium(db_path, browser, days)
            print(f"  → {len(rows)} entries")
            all_results.extend(rows)

    return sorted(all_results, key=lambda x: x["timestamp"])