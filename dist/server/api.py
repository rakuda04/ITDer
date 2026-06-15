"""
api.py  —  ITDer Dashboard API (server-side)
Serves data from Postgres instead of local CSVs.
Endpoints mirror the local version exactly so app.jsx needs no changes.

Run via Docker — see docker-compose.yml.
"""

import os
import json
import urllib.request

import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

DB_CONFIG = {
    "host":            os.getenv("POSTGRES_HOST",     "postgres"),
    "port":            int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname":          os.getenv("POSTGRES_DB",       "itder"),
    "user":            os.getenv("POSTGRES_USER",     "itder_user"),
    "password":        os.getenv("POSTGRES_PASSWORD", ""),
    "connect_timeout": 10,
}

WORKER_URL = os.getenv("WORKER_URL", "http://worker:8001")


def _connect():
    return psycopg2.connect(**DB_CONFIG)


def _query(sql, params=None):
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ── routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/users")
def users():
    include_synth = request.args.get("include_synthetic", "false").lower() == "true"
    synth_filter  = "" if include_synth else "WHERE ur.is_synthetic = 0"
    rows = _query(f"""
        SELECT DISTINCT ON (ur.username)
            ur.username                 AS user,
            ur.rank,
            ur.is_synthetic,
            ur.days_above_threshold,
            ur.final_risk_score,
            ur.supervised_max,
            ur.supervised_mean,
            ur.unsupervised_max,
            ur.unsupervised_mean,
            ur.iso_score_norm_mean,
            ur.ee_score_norm_mean,
            ur.days_flagged_iso,
            ur.days_flagged_ee,
            ur.days_flagged_both,
            ur.total_days,
            ur.peak_date,
            ur.composite_rank_score
        FROM user_risk ur
        JOIN pipeline_runs pr ON pr.run_id = ur.run_id
        {synth_filter}
        ORDER BY ur.username, pr.started_at DESC
    """)
    # coerce types
    int_cols   = ("rank","is_synthetic","days_above_threshold","days_flagged_iso",
                  "days_flagged_ee","days_flagged_both","total_days")
    float_cols = ("final_risk_score","supervised_max","supervised_mean",
                  "unsupervised_max","unsupervised_mean","iso_score_norm_mean",
                  "ee_score_norm_mean","composite_rank_score")
    for r in rows:
        for c in int_cols:
            try:    r[c] = int(r[c]) if r[c] is not None else 0
            except: r[c] = 0
        for c in float_cols:
            try:    r[c] = float(r[c]) if r[c] is not None else 0.0
            except: r[c] = 0.0
        if r.get("peak_date"):
            r["peak_date"] = str(r["peak_date"])
    return jsonify(rows)


@app.route("/api/daily")
def daily():
    include_synth = request.args.get("include_synthetic", "false").lower() == "true"
    synth_filter  = "" if include_synth else "WHERE ds.is_synthetic = 0"
    rows = _query(f"""
        SELECT DISTINCT ON (ds.username, ds.score_date)
            ds.username                 AS user,
            ds.score_date               AS date,
            ds.supervised_score,
            ds.unsupervised_score,
            ds.combined_risk_score,
            ds.iso_prediction,
            ds.iso_score,
            ds.iso_score_norm,
            ds.ee_prediction,
            ds.ee_score,
            ds.ee_score_norm,
            ds.flagged_by_both,
            ds.above_threshold,
            ds.is_synthetic,
            df.after_hours_session_count,
            df.weekend_session_flag,
            df.logon_count_zscore,
            df.logon_count_zscore_has_baseline,
            df.usb_count,
            df.usb_after_hours_flag,
            df.usb_on_weekend_flag,
            df.usb_device_diversity_monthly,
            df.usb_count_zscore,
            df.usb_count_zscore_has_baseline,
            df.job_site_visits_flag,
            df.job_search_plus_usb_week,
            df.total_active_minutes_day
        FROM daily_scores ds
        LEFT JOIN daily_features df
            ON df.username = ds.username
            AND df.feature_date = ds.score_date
        {synth_filter}
        ORDER BY ds.username, ds.score_date, ds.run_id DESC
    """)
    int_cols   = ("after_hours_session_count","weekend_session_flag","is_synthetic",
                  "iso_prediction","ee_prediction","flagged_by_both","above_threshold",
                  "job_site_visits_flag","job_search_plus_usb_week","usb_after_hours_flag",
                  "usb_on_weekend_flag","logon_count_zscore_has_baseline","usb_count_zscore_has_baseline")
    float_cols = ("total_active_minutes_day","logon_count_zscore","usb_count",
                  "usb_device_diversity_monthly","usb_count_zscore","supervised_score",
                  "unsupervised_score","combined_risk_score","iso_score","ee_score",
                  "iso_score_norm","ee_score_norm")
    for r in rows:
        for c in int_cols:
            try:    r[c] = int(r[c]) if r[c] is not None else 0
            except: r[c] = 0
        for c in float_cols:
            try:    r[c] = float(r[c]) if r[c] is not None else 0.0
            except: r[c] = 0.0
        if r.get("date"):
            r["date"] = str(r["date"])
    return jsonify(rows)


@app.route("/api/shap")
def shap():
    rows = _query("""
        SELECT DISTINCT ON (sv.username, sv.score_date)
            sv.username AS user,
            sv.score_date AS date,
            sv.after_hours_session_count,
            sv.weekend_session_flag,
            sv.logon_count_zscore,
            sv.logon_count_zscore_has_baseline,
            sv.usb_count,
            sv.usb_after_hours_flag,
            sv.usb_on_weekend_flag,
            sv.usb_device_diversity_monthly,
            sv.usb_count_zscore,
            sv.job_site_visits_flag,
            sv.job_search_plus_usb_week
        FROM shap_values sv
        ORDER BY sv.username, sv.score_date, sv.run_id DESC
    """)
    shap_cols = (
        "after_hours_session_count", "weekend_session_flag", "logon_count_zscore",
        "logon_count_zscore_has_baseline", "usb_count", "usb_after_hours_flag",
        "usb_on_weekend_flag", "usb_device_diversity_monthly", "usb_count_zscore",
        "job_site_visits_flag", "job_search_plus_usb_week",
    )
    for r in rows:
        for c in shap_cols:
            try:    r[c] = float(r[c]) if r[c] is not None else 0.0
            except: r[c] = 0.0
        if r.get("date"):
            r["date"] = str(r["date"])
    return jsonify(rows)


@app.route("/api/schedule", methods=["GET"])
def get_schedule():
    return jsonify({
        "enabled": os.getenv("ITDER_SCHEDULE", "0") == "1",
        "cron":    os.getenv("ITDER_CRON", "0 2 * * *"),
    })


@app.route("/api/schedule", methods=["POST"])
def set_schedule():
    # Schedule is configured via env vars in docker-compose.yml
    # This endpoint exists so the frontend doesn't 404
    return jsonify({"ok": True, "msg": "Schedule is configured via ITDER_SCHEDULE and ITDER_CRON env vars"})


@app.route("/api/status")
def status():
    try:
        _query("SELECT 1")
        db_ok = True
    except Exception as e:
        db_ok = False
    return jsonify({"db": db_ok})


@app.route("/api/run/synthetic", methods=["POST"])
def run_synthetic():
    """Trigger the worker to re-run synthetic generation + inference"""
    return _trigger_worker()


@app.route("/api/run/inference", methods=["POST"])
def run_inference():
    """Trigger the worker to run inference"""
    return _trigger_worker()


def _trigger_worker():
    try:
        req = urllib.request.Request(
            f"{WORKER_URL}/run",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return jsonify({"ok": data.get("ok", True), "output": data.get("msg", "")})
    except Exception as e:
        return jsonify({"ok": False, "output": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)