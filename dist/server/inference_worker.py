"""
inference_worker.py  —  ITDer Server-Side Inference Worker

Pulls daily_features from Postgres, runs synthetic generation
and inference, then writes scores back to daily_scores and user_risk.

Schedule (disabled by default):
    Set ITDER_SCHEDULE=1 in environment to enable.
    Set ITDER_CRON="0 2 * * *" to customize (default: daily at 02:00 UTC).
"""

import os
import sys
import traceback
import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

sys.dont_write_bytecode = True

# ── config ───────────────────────────────────────────────────

WORKER_DIR = Path(__file__).resolve().parent / "worker_files"
OUTPUT_DIR = WORKER_DIR / "output"

SCHEDULE_ENABLED = os.getenv("ITDER_SCHEDULE", "0") == "1"
SCHEDULE_CRON    = os.getenv("ITDER_CRON", "0 2 * * *")

DB_CONFIG = {
    "host":            os.getenv("POSTGRES_HOST",     "postgres"),
    "port":            int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname":          os.getenv("POSTGRES_DB",       "itder"),
    "user":            os.getenv("POSTGRES_USER",     "itder_user"),
    "password":        os.getenv("POSTGRES_PASSWORD", ""),
    "connect_timeout": 10,
}

# ── logging ──────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [worker] {msg}", flush=True)


def fail(msg):
    log(f"FATAL: {msg}")
    sys.exit(1)


# ── db helpers ────────────────────────────────────────────────

def _connect():
    return psycopg2.connect(**DB_CONFIG)


def _safe_float(val):
    try:    return float(val)
    except: return None

def _safe_int(val):
    try:    return int(float(val))
    except: return None

def _safe_date(val):
    if not val or str(val).strip() in ("", "NaT", "nan"):
        return None
    try:    return pd.to_datetime(str(val)).date()
    except: return None


def _get_server_device(cur) -> str:
    hostname = "itder-server"
    cur.execute("SELECT device_id FROM devices WHERE hostname = %s", (hostname,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE devices SET last_seen_at = now() WHERE hostname = %s", (hostname,))
        return str(row[0])
    cur.execute("""
        INSERT INTO devices (hostname, windows_version, enrolled_at, last_seen_at)
        VALUES (%s, 'server', now(), now()) RETURNING device_id
    """, (hostname,))
    return str(cur.fetchone()[0])


# ── pull features ─────────────────────────────────────────────

def pull_features() -> pd.DataFrame:
    log("Pulling daily_features from Postgres...")
    conn = _connect()
    try:
        df = pd.read_sql("""
            SELECT
                username                        AS user,
                feature_date                    AS date,
                to_char(feature_date, 'MM/DD/YYYY') AS day,
                total_active_minutes_day,
                after_hours_session_count,
                weekend_session_flag,
                logon_count_zscore,
                logon_count_zscore_has_baseline,
                usb_count,
                usb_after_hours_flag,
                usb_on_weekend_flag,
                usb_device_diversity_monthly,
                usb_count_zscore,
                usb_count_zscore_has_baseline,
                job_site_visits_flag,
                job_search_plus_usb_week
            FROM daily_features
            ORDER BY username, feature_date
        """, conn)
    finally:
        conn.close()

    log(f"  → {len(df)} rows | {df['user'].nunique()} user(s): {df['user'].unique().tolist()}")
    return df


# ── write scores ──────────────────────────────────────────────

def write_scores(daily_df: pd.DataFrame, user_report: pd.DataFrame, shap_df: pd.DataFrame):
    log("Writing scores to Postgres...")
    conn = _connect()
    run_id = None
    try:
        with conn:
            with conn.cursor() as cur:
                device_id = _get_server_device(cur)

                cur.execute("""
                    INSERT INTO pipeline_runs (device_id, started_at, status)
                    VALUES (%s, now(), 'running') RETURNING run_id
                """, (device_id,))
                run_id = cur.fetchone()[0]

                # daily_scores — all users (real + synthetic)
                score_data = [(
                    device_id, run_id,
                    str(r['user']), _safe_date(r['date']),
                    _safe_float(r.get('supervised_score')),
                    _safe_float(r.get('unsupervised_score')),
                    _safe_float(r.get('combined_risk_score')),
                    _safe_int(r.get('iso_prediction')),
                    _safe_float(r.get('iso_score')),
                    _safe_float(r.get('iso_score_norm')),
                    _safe_int(r.get('lof_prediction')),
                    _safe_float(r.get('lof_score')),
                    _safe_float(r.get('lof_score_norm')),
                    _safe_int(r.get('flagged_by_both')),
                    _safe_int(r.get('above_threshold')),
                    _safe_int(r.get('is_synthetic')),
                ) for _, r in daily_df.iterrows()]

                if score_data:
                    execute_values(cur, """
                        INSERT INTO daily_scores (
                            device_id, run_id, username, score_date,
                            supervised_score, unsupervised_score, combined_risk_score,
                            iso_prediction, iso_score, iso_score_norm,
                            lof_prediction, lof_score, lof_score_norm,
                            flagged_by_both, above_threshold, is_synthetic
                        ) VALUES %s
                        ON CONFLICT (device_id, username, score_date, run_id) DO NOTHING
                    """, score_data)
                    real_count  = sum(1 for _, r in daily_df.iterrows() if not r.get('is_synthetic'))
                    synth_count = len(score_data) - real_count
                    log(f"  → {real_count} real + {synth_count} synthetic rows written to daily_scores")

                # user_risk — all users
                all_users = user_report.copy().reset_index()
                user_data = [(
                    device_id, run_id,
                    str(r['user']),
                    _safe_int(r.get('rank')),
                    _safe_int(r.get('is_synthetic')),
                    _safe_int(r.get('days_above_threshold')),
                    _safe_float(r.get('final_risk_score')),
                    _safe_float(r.get('supervised_max')),
                    _safe_float(r.get('supervised_mean')),
                    _safe_float(r.get('unsupervised_max')),
                    _safe_float(r.get('unsupervised_mean')),
                    _safe_float(r.get('iso_score_norm_mean')),
                    _safe_float(r.get('lof_score_norm_mean')),
                    _safe_int(r.get('days_flagged_iso')),
                    _safe_int(r.get('days_flagged_lof')),
                    _safe_int(r.get('days_flagged_both')),
                    _safe_int(r.get('total_days')),
                    _safe_date(r.get('peak_date')),
                    _safe_float(r.get('composite_rank_score')),
                ) for _, r in all_users.iterrows()]

                if user_data:
                    execute_values(cur, """
                        INSERT INTO user_risk (
                            device_id, run_id, username,
                            rank, is_synthetic, days_above_threshold, final_risk_score,
                            supervised_max, supervised_mean, unsupervised_max, unsupervised_mean,
                            iso_score_norm_mean, lof_score_norm_mean,
                            days_flagged_iso, days_flagged_lof, days_flagged_both,
                            total_days, peak_date, composite_rank_score
                        ) VALUES %s
                        ON CONFLICT (device_id, username, run_id) DO NOTHING
                    """, user_data)
                    log(f"  → {len(user_data)} rows written to user_risk")

                # shap_values — real users only
                if shap_df is not None and not shap_df.empty:
                    real_shap = shap_df[shap_df['is_synthetic'] == 0].copy() if 'is_synthetic' in shap_df.columns else shap_df.copy()
                    shap_data = [(
                        device_id, run_id,
                        str(r['user']), _safe_date(r.get('date')),
                        _safe_float(r.get('after_hours_session_count')),
                        _safe_float(r.get('weekend_session_flag')),
                        _safe_float(r.get('logon_count_zscore')),
                        _safe_float(r.get('logon_count_zscore_has_baseline')),
                        _safe_float(r.get('usb_count')),
                        _safe_float(r.get('usb_after_hours_flag')),
                        _safe_float(r.get('usb_on_weekend_flag')),
                        _safe_float(r.get('usb_device_diversity_monthly')),
                        _safe_float(r.get('usb_count_zscore')),
                        _safe_float(r.get('job_site_visits_flag')),
                        _safe_float(r.get('job_search_plus_usb_week')),
                    ) for _, r in real_shap.iterrows()]

                    if shap_data:
                        execute_values(cur, """
                            INSERT INTO shap_values (
                                device_id, run_id, username, score_date,
                                after_hours_session_count, weekend_session_flag,
                                logon_count_zscore, logon_count_zscore_has_baseline,
                                usb_count, usb_after_hours_flag, usb_on_weekend_flag,
                                usb_device_diversity_monthly, usb_count_zscore,
                                job_site_visits_flag, job_search_plus_usb_week
                            ) VALUES %s
                            ON CONFLICT (device_id, username, score_date, run_id) DO NOTHING
                        """, shap_data)
                        log(f"  → {len(shap_data)} rows written to shap_values")

                cur.execute("""
                    UPDATE pipeline_runs
                    SET finished_at = now(), status = 'success', events_inserted = %s
                    WHERE run_id = %s
                """, (len(score_data) + len(user_data), run_id))

        log(f"  → Run {run_id} complete.")

    except Exception as e:
        traceback.print_exc()
        if run_id is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE pipeline_runs
                        SET finished_at = now(), status = 'failed', error_message = %s
                        WHERE run_id = %s
                    """, (str(e), run_id))
                conn.commit()
            except Exception:
                pass
        raise
    finally:
        conn.close()


# ── inference ─────────────────────────────────────────────────

def _load_module(name, path):
    spec   = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_inference(features_df: pd.DataFrame):
    log("Loading inference modules...")
    if str(WORKER_DIR) not in sys.path:
        sys.path.insert(0, str(WORKER_DIR))

    synth_mod = _load_module("synthetic_generator", WORKER_DIR / "synthetic_generator.py")
    infer_mod = _load_module("inference",           WORKER_DIR / "inference.py")

    synth_mod.CERT_INTAKE   = WORKER_DIR / "cert_pipeline/output/model_intake_final.csv"
    synth_mod.CERT_BASELINE = WORKER_DIR / "cert_pipeline/output/cert_baseline_stats.json"
    synth_mod.OUTPUT_PATH   = OUTPUT_DIR / "synthetic_population.csv"

    infer_mod.OUTPUT_DIR      = OUTPUT_DIR
    infer_mod.MODEL_DIR       = WORKER_DIR / "cert_pipeline/output/models"
    infer_mod.THRESHOLDS_FILE = WORKER_DIR / "cert_pipeline/output/cert_thresholds.json"
    infer_mod.LOCAL_FEATURES  = OUTPUT_DIR / "local_model_intake.csv"
    infer_mod.SYNTHETIC_POP   = OUTPUT_DIR / "synthetic_population.csv"
    infer_mod.OUTPUT_DAILY    = OUTPUT_DIR / "local_report_daily.csv"
    infer_mod.OUTPUT_USERS    = OUTPUT_DIR / "local_report_users.csv"
    infer_mod.OUTPUT_SHAP     = OUTPUT_DIR / "local_shap_values.csv"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    features_df.to_csv(infer_mod.LOCAL_FEATURES, index=False)
    log(f"  → Wrote {len(features_df)} feature rows to local_model_intake.csv")

    log("Running synthetic_generator...")
    synth_mod.generate(OUTPUT_DIR / "synthetic_population.csv")

    log("Running inference...")
    daily_df, user_report, shap_df = infer_mod.run()

    return daily_df, user_report, shap_df


# ── main job ──────────────────────────────────────────────────

def run_job():
    log("=" * 50)
    log("Inference worker started")
    log("=" * 50)
    try:
        features_df                      = pull_features()
        daily_df, user_report, shap_df   = run_inference(features_df)
        write_scores(daily_df, user_report, shap_df)
        log("Worker finished successfully.")
    except Exception as e:
        log(f"Worker failed: {e}")
        traceback.print_exc()
        sys.exit(1)


# ── http server ───────────────────────────────────────────────

from flask import Flask as _Flask, jsonify as _jsonify
import threading as _threading

_flask_app = _Flask(__name__)
_run_lock  = _threading.Lock()


@_flask_app.route("/run", methods=["POST"])
def http_run():
    if not _run_lock.acquire(blocking=False):
        return _jsonify({"ok": False, "msg": "run already in progress"}), 429
    def do_run():
        try:
            run_job()
        finally:
            _run_lock.release()
    _threading.Thread(target=do_run, daemon=True).start()
    return _jsonify({"ok": True, "msg": "inference started"})


@_flask_app.route("/health", methods=["GET"])
def http_health():
    return _jsonify({"status": "ok"})


# ── entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if SCHEDULE_ENABLED:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        parts = SCHEDULE_CRON.split()
        if len(parts) != 5:
            fail(f"Invalid ITDER_CRON '{SCHEDULE_CRON}'. Expected: 'min hour dom month dow'")

        trigger   = CronTrigger(minute=parts[0], hour=parts[1], day=parts[2],
                                 month=parts[3], day_of_week=parts[4])
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(run_job, trigger)
        scheduler.start()
        log(f"Scheduler enabled — cron: '{SCHEDULE_CRON}' (UTC)")
    else:
        log("Scheduler disabled — manual trigger only via HTTP")

    log("Worker HTTP server starting on port 8001")
    _flask_app.run(host="0.0.0.0", port=8001, debug=False)