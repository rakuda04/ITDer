"""
ingest_api.py  —  Receives pipeline results from Windows devices
                  and writes them to Postgres.

Endpoints:
    POST /ingest       —  upload features, scores, user_risk for one run
    GET  /health       —  liveness check

Run via docker compose — see docker-compose.yml.
"""

import os
import traceback

import psycopg2
from psycopg2.extras import execute_values
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import json
import time

app = Flask(__name__)
CORS(app)

DB_CONFIG = {
    "host":     os.getenv("POSTGRES_HOST",     "postgres"),
    "port":     int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname":   os.getenv("POSTGRES_DB",       "itder"),
    "user":     os.getenv("POSTGRES_USER",     "itder_user"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "connect_timeout": 10,
}


# ── db helpers ───────────────────────────────────────────────

def _connect():
    return psycopg2.connect(**DB_CONFIG)


def _safe_int(val):
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_date(val):
    if not val or str(val).strip() == "":
        return None
    try:
        from dateutil import parser
        return parser.parse(str(val)).date()
    except Exception:
        return None


def _get_or_create_device(cur, hostname: str, windows_version: str) -> str:
    cur.execute("SELECT device_id FROM devices WHERE hostname = %s", (hostname,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE devices SET last_seen_at = now(), windows_version = %s WHERE hostname = %s",
            (windows_version, hostname)
        )
        return str(row[0])
    cur.execute(
        """
        INSERT INTO devices (hostname, windows_version, enrolled_at, last_seen_at)
        VALUES (%s, %s, now(), now())
        RETURNING device_id
        """,
        (hostname, windows_version)
    )
    return str(cur.fetchone()[0])


def _open_run(cur, device_id: str) -> int:
    cur.execute(
        "INSERT INTO pipeline_runs (device_id, started_at, status) VALUES (%s, now(), 'running') RETURNING run_id",
        (device_id,)
    )
    return cur.fetchone()[0]


def _close_run(cur, run_id: int, status: str, error: str = None, inserted: int = None):
    cur.execute(
        """
        UPDATE pipeline_runs
        SET finished_at = now(), status = %s, error_message = %s, events_inserted = %s
        WHERE run_id = %s
        """,
        (status, error, inserted, run_id)
    )


def _insert_features(cur, rows: list, device_id: str, run_id: int) -> int:
    data = [(
        device_id, run_id,
        r.get("user"), _safe_date(r.get("date")),
        _safe_float(r.get("total_active_minutes_day")),
        _safe_int(r.get("after_hours_session_count")),
        _safe_int(r.get("weekend_session_flag")),
        _safe_float(r.get("logon_count_zscore")),
        _safe_int(r.get("logon_count_zscore_has_baseline")),
        _safe_float(r.get("usb_count")),
        _safe_int(r.get("usb_after_hours_flag")),
        _safe_int(r.get("usb_on_weekend_flag")),
        _safe_float(r.get("usb_device_diversity_monthly")),
        _safe_float(r.get("usb_count_zscore")),
        _safe_int(r.get("usb_count_zscore_has_baseline")),
        _safe_int(r.get("job_site_visits_flag")),
        _safe_int(r.get("job_search_plus_usb_week")),
    ) for r in rows]

    execute_values(cur, """
        INSERT INTO daily_features (
            device_id, run_id, username, feature_date,
            total_active_minutes_day, after_hours_session_count, weekend_session_flag,
            logon_count_zscore, logon_count_zscore_has_baseline,
            usb_count, usb_after_hours_flag, usb_on_weekend_flag,
            usb_device_diversity_monthly, usb_count_zscore, usb_count_zscore_has_baseline,
            job_site_visits_flag, job_search_plus_usb_week
        ) VALUES %s
        ON CONFLICT (device_id, username, feature_date) DO NOTHING
    """, data)
    return len(data)


def _insert_scores(cur, rows: list, device_id: str, run_id: int) -> int:
    data = [(
        device_id, run_id,
        r.get("user"), _safe_date(r.get("date")),
        _safe_float(r.get("supervised_score")),
        _safe_float(r.get("unsupervised_score")),
        _safe_float(r.get("combined_risk_score")),
        _safe_int(r.get("iso_prediction")),
        _safe_float(r.get("iso_score")),
        _safe_float(r.get("iso_score_norm")),
        _safe_int(r.get("ee_prediction")),
        _safe_float(r.get("ee_score")),
        _safe_float(r.get("ee_score_norm")),
        _safe_int(r.get("flagged_by_both")),
        _safe_int(r.get("above_threshold")),
        _safe_int(r.get("is_synthetic")),
    ) for r in rows]

    execute_values(cur, """
        INSERT INTO daily_scores (
            device_id, run_id, username, score_date,
            supervised_score, unsupervised_score, combined_risk_score,
            iso_prediction, iso_score, iso_score_norm,
            ee_prediction, ee_score, ee_score_norm,
            flagged_by_both, above_threshold, is_synthetic
        ) VALUES %s
        ON CONFLICT (device_id, username, score_date, run_id) DO NOTHING
    """, data)
    return len(data)


def _insert_user_risk(cur, rows: list, device_id: str, run_id: int) -> int:
    data = [(
        device_id, run_id,
        r.get("user"),
        _safe_int(r.get("rank")),
        _safe_int(r.get("is_synthetic")),
        _safe_int(r.get("days_above_threshold")),
        _safe_float(r.get("final_risk_score")),
        _safe_float(r.get("supervised_max")),
        _safe_float(r.get("supervised_mean")),
        _safe_float(r.get("unsupervised_max")),
        _safe_float(r.get("unsupervised_mean")),
        _safe_float(r.get("iso_score_norm_mean")),
        _safe_float(r.get("ee_score_norm_mean")),
        _safe_int(r.get("days_flagged_iso")),
        _safe_int(r.get("days_flagged_ee")),
        _safe_int(r.get("days_flagged_both")),
        _safe_int(r.get("total_days")),
        _safe_date(r.get("peak_date")),
        _safe_float(r.get("composite_rank_score")),
    ) for r in rows]

    execute_values(cur, """
        INSERT INTO user_risk (
            device_id, run_id, username,
            rank, is_synthetic, days_above_threshold, final_risk_score,
            supervised_max, supervised_mean, unsupervised_max, unsupervised_mean,
            iso_score_norm_mean, ee_score_norm_mean,
            days_flagged_iso, days_flagged_ee, days_flagged_both,
            total_days, peak_date, composite_rank_score
        ) VALUES %s
        ON CONFLICT (device_id, username, run_id) DO NOTHING
    """, data)
    return len(data)


# ── routes ───────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/ingest")
def ingest():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "expected JSON body"}), 400

    hostname        = body.get("hostname", "unknown")
    windows_version = body.get("windows_version", "")
    features        = body.get("features", [])
    scores          = body.get("scores", [])
    user_risk       = body.get("user_risk", [])

    if not any([features, scores, user_risk]):
        return jsonify({"error": "no data provided"}), 400

    run_id = None
    try:
        conn = _connect()
        with conn:
            with conn.cursor() as cur:
                device_id = _get_or_create_device(cur, hostname, windows_version)
                run_id    = _open_run(cur, device_id)

                n_feat   = _insert_features(cur,  features,  device_id, run_id) if features  else 0
                n_scores = _insert_scores(cur,    scores,    device_id, run_id) if scores    else 0
                n_users  = _insert_user_risk(cur, user_risk, device_id, run_id) if user_risk else 0

                total = n_feat + n_scores + n_users
                _close_run(cur, run_id, "success", inserted=total)

        conn.close()
        timestamp = time.strftime("%H:%M:%S")
        SYSTEM_LOGS.append({"timestamp": timestamp, "source": "api", "message": f"Ingested {total} rows from {hostname}"})
        if len(SYSTEM_LOGS) > 1000: SYSTEM_LOGS.pop(0)
        return jsonify({"status": "ok", "run_id": run_id, "rows_inserted": total})

    except Exception as e:
        traceback.print_exc()
        if run_id is not None:
            try:
                with conn.cursor() as cur:
                    _close_run(cur, run_id, "failed", error=str(e))
                conn.commit()
            except Exception:
                pass
        return jsonify({"error": str(e)}), 500

SYSTEM_LOGS = []

@app.route("/api/telemetry", methods=["POST"])
def post_telemetry():
    payload = request.get_json(silent=True) or {}
    msg = payload.get("message", "")
    source = payload.get("source", "unknown")
    if msg:
        timestamp = time.strftime("%H:%M:%S")
        SYSTEM_LOGS.append({"timestamp": timestamp, "source": source, "message": msg})
        if len(SYSTEM_LOGS) > 1000:
            SYSTEM_LOGS.pop(0)
    return jsonify({"ok": True})

@app.route("/api/telemetry_stream")
def telemetry_stream():
    def generate():
        last_idx = max(0, len(SYSTEM_LOGS) - 50)
        yield f"data: {json.dumps(SYSTEM_LOGS[last_idx:])}\n\n"
        last_idx = len(SYSTEM_LOGS)
        while True:
            current_len = len(SYSTEM_LOGS)
            if current_len > last_idx:
                new_logs = SYSTEM_LOGS[last_idx:current_len]
                yield f"data: {json.dumps(new_logs)}\n\n"
                last_idx = current_len
            elif current_len < last_idx:
                last_idx = len(SYSTEM_LOGS)
            time.sleep(0.5)
    return Response(generate(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
