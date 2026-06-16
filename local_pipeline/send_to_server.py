# ============================================================
# send_to_server.py  —  Upload pipeline results to server
#
# Reads the 3 output CSVs and POSTs them to the ingest API.
# No database credentials needed on the Windows device.
#
# Usage:
#   python send_to_server.py
#
# Config:
#   Set ITDER_API_URL to your Cloudflare Tunnel URL.
#
# Requires:
#   pip install requests pandas
# ============================================================

import os
import sys
import socket
import platform
from pathlib import Path

import pandas as pd
import requests

sys.dont_write_bytecode = True

API_URL  = os.getenv("ITDER_API_URL", "https://your-tunnel.trycloudflare.com")
ENDPOINT = f"{API_URL.rstrip('/')}/ingest"

SCRIPT_DIR   = Path(__file__).resolve().parent
OUTPUT_DIR   = SCRIPT_DIR / "output"
DAILY_CSV    = OUTPUT_DIR / "local_report_daily.csv"
USERS_CSV    = OUTPUT_DIR / "local_report_users.csv"
FEATURES_CSV = OUTPUT_DIR / "local_model_intake.csv"


def run():
    if not FEATURES_CSV.exists():
        print(f"[server] Missing output features file: {FEATURES_CSV}")
        print("[server] Run the pipeline first.")
        sys.exit(1)

    print("[server] Loading CSVs...")
    features  = pd.read_csv(FEATURES_CSV).fillna("").to_dict(orient="records")
    
    scores = []
    if DAILY_CSV.exists():
        scores = pd.read_csv(DAILY_CSV).fillna("").to_dict(orient="records")
        
    user_risk = []
    if USERS_CSV.exists():
        user_risk = pd.read_csv(USERS_CSV).fillna("").to_dict(orient="records")

    payload = {
        "hostname":        socket.gethostname(),
        "windows_version": platform.version(),
        "features":        features,
        "scores":          scores,
        "user_risk":       user_risk,
    }


    print(f"[server] Posting to {ENDPOINT}...")
    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"[server] Done. run_id={data.get('run_id')}  rows={data.get('rows_inserted')}")
    except requests.exceptions.ConnectionError:
        print("[server] Could not reach server. Check ITDER_API_URL and internet connection.")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"[server] Server returned error: {e.response.status_code} {e.response.text}")
        sys.exit(1)


if __name__ == "__main__":
    run()
