# ============================================================
# collectors/windows_events.py
#
# Responsibility: query Windows Event Log, parse XML, return
# a list of normalized dicts.  No filtering, no side-effects.
#
# Every entry this module returns has AT MINIMUM:
#   timestamp  – aware datetime object (local tz)
#   source     – str  ("UMDF" | "Security" | "System")
#   event_id   – int
#   user       – str
# Plus source-specific keys (device, activity, logon_id).
# ============================================================

import os
import xml.etree.ElementTree as ET
from datetime import datetime

import win32evtlog

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

# ── XML namespace used by all Windows event XML ─────────────
_NS = {'ns': 'http://schemas.microsoft.com/win/2004/08/events/event'}


# ── low-level query ──────────────────────────────────────────

def _run_evt_query(log_path: str, criteria: str, days_back: int) -> list:
    """Return raw event handles from a Windows Event Log channel."""
    ms_limit = days_back * 86_400_000
    xpath = (
        f"*[System[({criteria}) and "
        f"TimeCreated[timediff(@SystemTime) <= {ms_limit}]]]"
    )
    events = []
    try:
        handle = win32evtlog.EvtQuery(
            log_path,
            win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection,
            xpath,
        )
        while True:
            batch = win32evtlog.EvtNext(handle, 50)
            if not batch:
                break
            events.extend(batch)
    except Exception as exc:
        print(f"[windows_events] Error reading '{log_path}': {exc}")
    return events


def _parse_timestamp(utc_str: str) -> datetime:
    return datetime.fromisoformat(utc_str.replace("Z", "+00:00")).astimezone()


# ── public collectors ────────────────────────────────────────

def get_umdf_events(days: int = config.DAYS_BACK) -> list[dict]:
    """
    Collect USB device connect/disconnect events from the UMDF operational log.
    Returns one dict per event, sorted oldest-first.
    """
    ids = config.UMDF_EVENT_IDS
    criteria = " or ".join(f"EventID={eid}" for eid in ids)
    log_path = "Microsoft-Windows-DriverFrameworks-UserMode/Operational"

    raw_events = _run_evt_query(log_path, criteria, days)
    results = []

    for event in raw_events:
        xml_str = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
        root = ET.fromstring(xml_str)

        eid = int(root.find(".//ns:EventID", _NS).text)
        ts = _parse_timestamp(root.find(".//ns:TimeCreated", _NS).get("SystemTime"))
        instance_node = root.find(".//{*}InstanceId")

        results.append({
            "timestamp": ts,
            "source":    "UMDF",
            "event_id":  eid,
            "device":    instance_node.text if instance_node is not None else "N/A",
            "user":      os.getlogin(),
        })

    return sorted(results, key=lambda x: x["timestamp"])


def get_security_events(days: int = config.DAYS_BACK) -> list[dict]:
    """
    Collect logon/lock/unlock/sleep/wake/shutdown events.
    Returns one dict per event, sorted oldest-first.

    Note: a synthetic LOGON entry is NOT injected here anymore.
    If you need a startup marker, add it in pipeline.py so it
    is explicit and visible.
    """
    results = []

    for log_path, cfg in config.SECURITY_EVENT_CONFIG.items():
        criteria = " or ".join(f"EventID={eid}" for eid in cfg["ids"])
        raw_events = _run_evt_query(log_path, criteria, days)

        for event in raw_events:
            xml_str = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
            root = ET.fromstring(xml_str)

            eid = int(root.find(".//ns:EventID", _NS).text)
            ts = _parse_timestamp(root.find(".//ns:TimeCreated", _NS).get("SystemTime"))

            data_nodes = root.findall(".//ns:Data", _NS)
            event_data = {n.get("Name"): n.text for n in data_nodes if n.get("Name")}

            results.append({
                "timestamp": ts,
                "source":    log_path,          # "Security" or "System"
                "event_id":  eid,
                "activity":  cfg["labels"].get(eid, "OTHER"),
                "user":      os.getlogin(),
                "logon_id":  event_data.get("TargetLogonId", "n/a"),
            })

    return sorted(results, key=lambda x: x["timestamp"])