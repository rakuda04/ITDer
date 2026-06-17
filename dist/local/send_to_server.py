# ============================================================
# send_to_server.py  —  Upload preprocessed features to server
#
# Reads local_model_intake.csv and POSTs to the ingest API.
# Inference runs server-side — not on this device.
#
# Requires: pip install requests pandas
# ============================================================

import os
import sys
import socket
import platform
from pathlib import Path

import pandas as pd
import requests

sys.dont_write_bytecode = True

SCRIPT_DIR   = Path(__file__).resolve().parent
FEATURES_CSV = SCRIPT_DIR / "output" / "local_model_intake.csv"

# Read api_url.txt if it exists, otherwise fall back to environment variable or default
API_URL = "https://your-tunnel.yourdomain.com"
api_url_file = SCRIPT_DIR / "api_url.txt"
if api_url_file.exists():
    try:
        API_URL = api_url_file.read_text().strip()
    except Exception:
        API_URL = os.getenv("ITDER_API_URL", API_URL)
else:
    API_URL = os.getenv("ITDER_API_URL", API_URL)

ENDPOINT = f"{API_URL.rstrip('/')}/ingest"


def run():
    if not FEATURES_CSV.exists():
        print(f"[server] Missing: {FEATURES_CSV}")
        print("[server] Run local_preprocessor.py first.")
        sys.exit(1)

    print("[server] Loading features...")
    features = pd.read_csv(FEATURES_CSV).fillna("").to_dict(orient="records")

    payload = {
        "hostname":        socket.gethostname(),
        "windows_version": platform.version(),
        "features":        features,
    }

    print(f"[server] Posting {len(features)} rows to {ENDPOINT}...")
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