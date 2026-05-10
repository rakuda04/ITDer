"""
UEBA Local Pipeline API
Run: python api.py
Serves CSV data from local_pipeline/output/ as JSON endpoints.
"""

import os
import json
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import csv

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

# Resolve output directory relative to this file
BASE = Path(__file__).parent
OUTPUT_DIR = BASE.parent / "local_pipeline" / "output"


def read_csv(filename: str) -> list[dict]:
    path = OUTPUT_DIR / filename
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def coerce_users(rows):
    for r in rows:
        for col in ("rank", "is_synthetic", "days_flagged_iso", "days_flagged_lof", "days_flagged_both"):
            if col in r:
                try:
                    r[col] = int(r[col])
                except (ValueError, TypeError):
                    r[col] = 0
        for col in ("final_risk_score", "supervised_max", "supervised_mean", "unsupervised_max"):
            if col in r:
                try:
                    r[col] = float(r[col])
                except (ValueError, TypeError):
                    r[col] = 0.0
    return rows


def coerce_daily(rows):
    int_cols = (
        "after_hours_session_count", "weekend_session_flag", "is_synthetic",
        "iso_prediction", "lof_prediction", "flagged_by_both", "above_threshold",
        "job_site_visits_flag", "job_search_plus_usb_week",
        "usb_after_hours_flag", "usb_on_weekend_flag",
        "logon_count_zscore_has_baseline", "usb_count_zscore_has_baseline",
    )
    float_cols = (
        "total_active_minutes_day", "logon_count_zscore", "usb_count",
        "usb_device_diversity_monthly", "usb_count_zscore",
        "supervised_score", "unsupervised_score", "combined_risk_score",
        "iso_score", "lof_score", "iso_score_norm", "lof_score_norm",
    )
    for r in rows:
        for col in int_cols:
            if col in r:
                try:
                    r[col] = int(float(r[col]))
                except (ValueError, TypeError):
                    r[col] = 0
        for col in float_cols:
            if col in r:
                try:
                    r[col] = float(r[col])
                except (ValueError, TypeError):
                    r[col] = 0.0
    return rows


def coerce_shap(rows):
    shap_cols = (
        "after_hours_session_count", "weekend_session_flag", "logon_count_zscore",
        "logon_count_zscore_has_baseline", "usb_count", "usb_after_hours_flag",
        "usb_on_weekend_flag", "usb_device_diversity_monthly", "usb_count_zscore",
        "job_site_visits_flag", "job_search_plus_usb_week",
    )
    for r in rows:
        for col in shap_cols:
            if col in r:
                try:
                    r[col] = float(r[col])
                except (ValueError, TypeError):
                    r[col] = 0.0
    return rows


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/users")
def users():
    rows = coerce_users(read_csv("local_report_users.csv"))
    return jsonify(rows)


@app.route("/api/daily")
def daily():
    rows = coerce_daily(read_csv("local_report_daily.csv"))
    return jsonify(rows)


@app.route("/api/shap")
def shap():
    rows = coerce_shap(read_csv("local_shap_values.csv"))
    return jsonify(rows)


@app.route("/api/status")
def status():
    files = {
        "local_report_users.csv": (OUTPUT_DIR / "local_report_users.csv").exists(),
        "local_report_daily.csv": (OUTPUT_DIR / "local_report_daily.csv").exists(),
        "local_shap_values.csv": (OUTPUT_DIR / "local_shap_values.csv").exists(),
    }
    return jsonify({"output_dir": str(OUTPUT_DIR), "files": files})


if __name__ == "__main__":
    print(f"Reading CSVs from: {OUTPUT_DIR}")
    app.run(port=5000, debug=True)