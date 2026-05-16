# ============================================================
# infer.py  —  Local inference pipeline
#
# Loads trained CERT models and scores:
#   1. Real local user (from local_features.csv)
#   2. Synthetic population (from synthetic_population.csv)
#
# Stages:
#   Stage 1 — RF supervised (CERT-trained weights, no retraining)
#   Stage 2 — IsoForest (scored against combined population)
#   Stage 3 — LOF (scored against combined population)
#   Stage 4 — Combined risk score + SHAP explanations
#
# Note on LOF:
#   LOF is meaningful here because the synthetic population
#   provides a realistic neighborhood. Without it, LOF on a
#   single user would be meaningless.
#
# Note on normalization:
#   IsoForest and LOF raw scores are normalized using the min/max
#   ranges from CERT training (stored in cert_thresholds.json).
#   This ensures a score of 0.5 locally means the same thing as
#   0.5 on CERT — preventing the small local population from
#   compressing the scale and inflating everyone's score.
#
# Note on final_risk_score aggregation:
#   final_risk_score is the mean of combined_risk_score across all
#   days for a user, not the max. This prevents a single random
#   high-scoring day from inflating a normal user's overall risk.
#   Genuine insiders have sustained anomalous behavior across many
#   days, so their mean stays high. Normal users with one random
#   spike get averaged down.
#
# Outputs (to local_pipeline/output/):
#   local_report_daily.csv   — per-day scores for all users
#   local_report_users.csv   — aggregated per-user risk ranking
#   local_shap_values.csv    — SHAP feature attributions
# ============================================================

import sys
sys.dont_write_bytecode = True

import json
import pickle
import warnings
import numpy as np
import pandas as pd
import shap
from pathlib import Path
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings('ignore')

# ── paths ────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).resolve().parent
CERT_DIR      = SCRIPT_DIR.parent / "cert_pipeline"
OUTPUT_DIR    = SCRIPT_DIR / "output"
MODEL_DIR     = CERT_DIR / "output" / "models"

LOCAL_FEATURES   = OUTPUT_DIR / "local_model_intake.csv"
SYNTHETIC_POP    = OUTPUT_DIR / "synthetic_population.csv"
THRESHOLDS_FILE  = CERT_DIR / "output" / "cert_thresholds.json"

OUTPUT_DAILY     = OUTPUT_DIR / "local_report_daily.csv"
OUTPUT_USERS     = OUTPUT_DIR / "local_report_users.csv"
OUTPUT_SHAP      = OUTPUT_DIR / "local_shap_values.csv"

# ── config ───────────────────────────────────────────────────
CONFIG = {
    'weight_supervised':   0.7,
    'weight_unsupervised': 0.3,
    'lof_neighbors':       20,
    'shap_days_per_user':  3,
    'ignore_columns': [
        'user', 'date', 'day',
        'total_active_minutes_day',
        'usb_count_zscore_has_baseline',
        'is_synthetic', 'insider_label', 'scenario',
    ],
}

# ── load ─────────────────────────────────────────────────────

def _load_models():
    print("[infer] Loading trained models...")
    models = {}
    for name, fname in [
        ('rf',        'rf_supervised.pkl'),
        ('iso',       'iso_forest.pkl'),
        ('lof_scaler','lof_scaler.pkl'),
    ]:
        path = MODEL_DIR / fname
        if not path.exists():
            raise FileNotFoundError(f"Model not found: {path}. Run model_training.py first.")
        with open(path, 'rb') as f:
            models[name] = pickle.load(f)
        print(f"  ✓ {fname}")
    return models


def _load_thresholds():
    if not THRESHOLDS_FILE.exists():
        print(f"[infer] WARNING: cert_thresholds.json not found — using defaults")
        return {'recommended_threshold': 0.5}
    with open(THRESHOLDS_FILE) as f:
        t = json.load(f)
    print(f"[infer] Loaded thresholds — recommended: {t['recommended_threshold']:.4f}")

    # Warn if the score ranges are missing — means model_training.py needs to be rerun
    for key in ('iso_score_min', 'iso_score_max', 'lof_score_min', 'lof_score_max'):
        if key not in t:
            print(f"[infer] WARNING: '{key}' missing from cert_thresholds.json. "
                  f"Re-run model_training.py to regenerate thresholds with score ranges.")
    return t


def _load_data():
    print("[infer] Loading local features...")
    if not LOCAL_FEATURES.exists():
        raise FileNotFoundError(f"local_features.csv not found. Run preprocess.py first.")
    local = pd.read_csv(LOCAL_FEATURES)
    local['is_synthetic'] = 0
    if 'insider_label' not in local.columns:
        local['insider_label'] = -1   # -1 = unknown (real user, no label)
    if 'scenario' not in local.columns:
        local['scenario'] = None
    print(f"  → {len(local)} local rows | {local['user'].nunique()} real user(s)")

    print("[infer] Loading synthetic population...")
    if not SYNTHETIC_POP.exists():
        raise FileNotFoundError(f"synthetic_population.csv not found. Run synthetic_generator.py first.")
    synth = pd.read_csv(SYNTHETIC_POP)
    print(f"  → {len(synth)} synthetic rows | {synth['user'].nunique()} synthetic users")

    combined = pd.concat([local, synth], ignore_index=True)
    print(f"  → Combined: {len(combined)} rows | {combined['user'].nunique()} total users")
    return combined


def _prepare_features(df, feature_cols=None):
    exclude = set(CONFIG['ignore_columns'])
    if feature_cols is None:
        feature_cols = [c for c in df.columns if c not in exclude]

    X = df[feature_cols].copy()

    # Fill z-score NaNs with 0 (has_baseline columns signal quality)
    zscore_cols = [c for c in X.columns if 'zscore' in c or 'z_score' in c]
    X[zscore_cols] = X[zscore_cols].fillna(0)
    X = X.fillna(0)

    return X, feature_cols


# ── scoring ──────────────────────────────────────────────────

def _run_supervised(X, models, feature_cols):
    print("\n[infer] Stage 1: Supervised RF scoring...")
    saved       = models['rf']
    rf          = saved['model']
    train_cols  = saved['feature_cols']

    # Align columns to what RF was trained on
    missing = set(train_cols) - set(feature_cols)
    if missing:
        print(f"  [!] Missing features filled with 0: {missing}")
        for col in missing:
            X[col] = 0
    X_aligned = X[train_cols]

    scores = rf.predict_proba(X_aligned.values)[:, 1]
    print(f"  → Max supervised score: {scores.max():.4f}")
    return scores, train_cols


def _run_iso(X, models, feature_cols):
    print("[infer] Stage 2: IsoForest scoring...")
    iso    = models['iso']
    preds  = iso.predict(X.values)
    scores = iso.decision_function(X.values)
    print(f"  → Flagged {(preds == -1).sum()} rows")
    return preds, scores


def _run_lof(X, models):
    print("[infer] Stage 3: LOF scoring...")
    scaler   = models['lof_scaler']
    X_scaled = scaler.transform(X.values)
    lof      = LocalOutlierFactor(
        n_neighbors   = CONFIG['lof_neighbors'],
        contamination = 'auto',
        novelty       = False,
        n_jobs        = -1,
    )
    preds  = lof.fit_predict(X_scaled)
    scores = lof.negative_outlier_factor_
    print(f"  → Flagged {(preds == -1).sum()} rows")
    return preds, scores


def _build_combined(supervised, iso_scores, lof_scores, iso_preds, lof_preds, thresholds):
    print("[infer] Stage 4: Building combined risk score...")

    # Normalize using CERT training ranges so local scores are on the same
    # scale as CERT. Without this, local min/max compression inflates everyone.
    # Falls back to local min/max if thresholds were generated by an older
    # version of model_training.py that didn't save score ranges.
    if 'iso_score_min' in thresholds and 'iso_score_max' in thresholds:
        iso_min = thresholds['iso_score_min']
        iso_max = thresholds['iso_score_max']
        print(f"  → Using CERT iso range: [{iso_min:.4f}, {iso_max:.4f}]")
    else:
        iso_min = float(iso_scores.min())
        iso_max = float(iso_scores.max())
        print(f"  → WARNING: Using local iso range (re-run model_training.py for CERT anchoring)")

    if 'lof_score_min' in thresholds and 'lof_score_max' in thresholds:
        lof_min = thresholds['lof_score_min']
        lof_max = thresholds['lof_score_max']
        print(f"  → Using CERT lof range: [{lof_min:.4f}, {lof_max:.4f}]")
    else:
        lof_min = float(lof_scores.min())
        lof_max = float(lof_scores.max())
        print(f"  → WARNING: Using local lof range (re-run model_training.py for CERT anchoring)")

    # Invert so higher = more anomalous, then clip to [0,1] because local
    # scores can fall outside the CERT training range
    iso_norm = 1 - (iso_scores - iso_min) / (iso_max - iso_min + 1e-9)
    iso_norm = np.clip(iso_norm, 0, 1)

    lof_norm = 1 - (lof_scores - lof_min) / (lof_max - lof_min + 1e-9)
    lof_norm = np.clip(lof_norm, 0, 1)

    unsupervised = (iso_norm + lof_norm) / 2
    combined     = (CONFIG['weight_supervised']   * supervised +
                    CONFIG['weight_unsupervised'] * unsupervised)
    return combined, unsupervised, iso_norm, lof_norm


def _build_shap(rf, X_aligned, df, feature_cols):
    print("[infer] Building SHAP explanations...")
    explainer  = shap.TreeExplainer(rf)
    shap_vals  = explainer.shap_values(X_aligned.values)

    # shap_values returns [class0, class1] list or 3D array for binary RF
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[1]
    elif shap_vals.ndim == 3:
        shap_vals = shap_vals[:, :, 1]

    shap_df = pd.DataFrame(shap_vals, columns=feature_cols)
    shap_df.insert(0, 'user', df['user'].values)
    shap_df.insert(1, 'date', df['date'].values)
    return shap_df


# ── reports ──────────────────────────────────────────────────

def _build_user_report(df):
    agg = df.groupby(['user', 'is_synthetic']).agg(
        # Mean across all days — prevents one random high-scoring day from
        # inflating a normal user's overall risk score. Genuine insiders
        # have sustained anomalous behavior so their mean stays high.
        final_risk_score  =('combined_risk_score', 'mean'),
        supervised_max    =('supervised_score',    'max'),
        supervised_mean   =('supervised_score',    'mean'),
        unsupervised_max  =('unsupervised_score',  'max'),
        days_flagged_iso  =('iso_prediction',      lambda x: (x == -1).sum()),
        days_flagged_lof  =('lof_prediction',      lambda x: (x == -1).sum()),
        days_flagged_both =('flagged_by_both',     'sum'),
    ).reset_index()

    # Peak date is still based on the single highest combined score day
    # so analysts can drill into the most anomalous moment
    peak = (df.loc[df.groupby('user')['combined_risk_score'].idxmax(),
                   ['user', 'day']].rename(columns={'day': 'peak_date'}))
    agg  = agg.merge(peak, on='user', how='left')
    agg  = agg.sort_values('final_risk_score', ascending=False).reset_index(drop=True)
    agg.index += 1
    agg.index.name = 'rank'
    return agg


# ── main ─────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("  LOCAL INFERENCE PIPELINE")
    print("=" * 60)

    models     = _load_models()
    thresholds = _load_thresholds()
    df         = _load_data()

    X, feature_cols = _prepare_features(df)

    # Stage 1 — Supervised
    supervised_scores, aligned_cols = _run_supervised(X, models, feature_cols)

    # Re-align X for unsupervised (same columns RF used)
    X_aligned = X[aligned_cols].fillna(0)

    # Stage 2 — IsoForest
    iso_preds, iso_scores = _run_iso(X_aligned, models, aligned_cols)

    # Stage 3 — LOF
    lof_preds, lof_scores = _run_lof(X_aligned, models)

    # Stage 4 — Combined (uses CERT score ranges from thresholds)
    combined, unsupervised, iso_norm, lof_norm = _build_combined(
        supervised_scores, iso_scores, lof_scores, iso_preds, lof_preds, thresholds
    )

    # Attach scores to df
    df['supervised_score']    = supervised_scores
    df['unsupervised_score']  = unsupervised
    df['combined_risk_score'] = combined
    df['iso_prediction']      = iso_preds
    df['iso_score']           = iso_scores
    df['lof_prediction']      = lof_preds
    df['lof_score']           = lof_scores
    df['iso_score_norm']      = iso_norm
    df['lof_score_norm']      = lof_norm
    df['flagged_by_both']     = ((iso_preds == -1) & (lof_preds == -1)).astype(int)
    df['above_threshold']     = (combined >= thresholds['recommended_threshold']).astype(int)

    # SHAP
    rf         = models['rf']['model']
    shap_df    = _build_shap(rf, X_aligned, df, aligned_cols)

    # Reports
    user_report = _build_user_report(df)

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DAILY, index=False)
    user_report.to_csv(OUTPUT_USERS)
    shap_df.to_csv(OUTPUT_SHAP, index=False)

    print(f"\n[infer] ✅ Outputs saved:")
    print(f"  Per-day report : {OUTPUT_DAILY}")
    print(f"  User report    : {OUTPUT_USERS}")
    print(f"  SHAP values    : {OUTPUT_SHAP}")

    # ── console summary ───────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESULTS — REAL USERS ONLY")
    print(f"{'='*60}")
    real_users = user_report[user_report['is_synthetic'] == 0]
    if real_users.empty:
        print("  No real users in report.")
    else:
        print(real_users[[
            'user', 'peak_date', 'final_risk_score',
            'supervised_mean', 'days_flagged_both'
        ]].to_string())

    threshold = thresholds['recommended_threshold']
    print(f"\n  CERT p98 threshold : {threshold:.4f}")
    print(f"  Days above threshold (real users): "
          f"{df[(df['is_synthetic']==0) & (df['above_threshold']==1)].shape[0]}")

    return df, user_report, shap_df


if __name__ == "__main__":
    run()