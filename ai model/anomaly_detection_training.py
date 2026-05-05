import pandas as pd
import numpy as np
import os
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

# --- PATH CALCULATION ---
# This finds the 'ai model' folder where this script lives
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Goes back one level to the 'clean-repo' root
BASE_PROJECT_PATH = os.path.dirname(SCRIPT_DIR)

# --- CONFIGURATION ---
CONFIG = {
    'base_path': BASE_PROJECT_PATH,
    'input_file': 'model_intake_final.csv',
    'output_file_rows': 'anomaly_report_daily.csv',    # one row per user-day
    'output_file_users': 'anomaly_report_users.csv',   # one row per user (the useful one)

    # Contamination: expected fraction of genuinely anomalous rows.
    # This is a model hint, not a false-positive knob — tuning it down
    # just moves the threshold, it doesn't improve feature quality.
    # Start at 0.02 and lower only after confirming feature validity.
    'contamination': 0.02,

    # LOF: how many neighbors to consider when judging local density.
    # Lower = more sensitive to micro-clusters, higher = more global view.
    # 20 is a reasonable default for this dataset size.
    'lof_neighbors': 20,

    # Columns that are identifiers, not features
    'ignore_columns': ['user', 'date', 'day'],

    # Features that need scaling (distance-based model: LOF).
    # IsolationForest does NOT get scaled — it's tree-based and scale-invariant,
    # and scaling would distort the 999 sentinel in days_since_last_usb.
    # LOF uses Euclidean distance so it DOES need scaling.
    'scale_for_lof': True,

    # Top N users to show in the console report
    'report_top_n': 20,
}


# =============================================================================
# 1. LOAD & PREPARE
# =============================================================================

def load_data():
    path = os.path.join(CONFIG['base_path'], CONFIG['input_file'])
    print(f"Loading data from: {path}...")
    if not os.path.exists(path):
        raise FileNotFoundError("CRITICAL: Input file not found. Run preprocessor.py first.")
    return pd.read_csv(path)


def prepare_features(df):
    """
    Select feature columns and handle NaN values left intentionally by
    the preprocessor for sparse z-score users.

    NaN strategy:
    - Z-score columns: fill with 0 AFTER using the companion has_baseline
      column as a feature. The has_baseline flag tells the model this score
      is untrustworthy, so filling the score itself with 0 is safe.
    - All other columns should already be non-NaN from the preprocessor's
      selective fillna step. If any remain, fill with 0 and warn.
    """
    feature_cols = [c for c in df.columns if c not in CONFIG['ignore_columns']]
    X = df[feature_cols].copy()

    # Fill NaN in z-score columns with 0 (has_baseline columns explain the gap)
    zscore_cols = [c for c in X.columns if 'zscore' in c or 'z_score' in c]
    X[zscore_cols] = X[zscore_cols].fillna(0)

    # Catch any remaining NaNs and warn — these shouldn't exist post-preprocessor
    remaining_nan = X.isnull().sum()
    remaining_nan = remaining_nan[remaining_nan > 0]
    if not remaining_nan.empty:
        print(f"  WARNING: Unexpected NaNs found and filled with 0: {remaining_nan.to_dict()}")
        X = X.fillna(0)

    print(f"\nFeatures in use ({len(feature_cols)}):")
    for col in feature_cols:
        print(f"  - {col}")

    return X, feature_cols


# =============================================================================
# 2. MODELS
# =============================================================================

def run_isolation_forest(X):
    """
    IsolationForest: detects global outliers by measuring how easy it is to
    isolate a point from the rest of the data using random splits.

    NOT scaled — tree-based models are scale-invariant and scaling would
    distort the 999 sentinel value in days_since_last_usb.

    Returns:
        predictions: array of 1 (normal) or -1 (anomaly)
        scores: continuous decision scores — more negative = more anomalous
    """
    print(f"\nTraining Isolation Forest (contamination={CONFIG['contamination']})...")
    model = IsolationForest(
        contamination=CONFIG['contamination'],
        n_estimators=200,       # more trees = more stable scores
        max_samples='auto',
        random_state=42,
        n_jobs=-1               # use all CPU cores
    )
    predictions = model.fit_predict(X)
    scores = model.decision_function(X)
    flagged = (predictions == -1).sum()
    print(f"  Isolation Forest flagged {flagged:,} rows ({flagged/len(X)*100:.2f}%)")
    return predictions, scores


def run_lof(X):
    """
    Local Outlier Factor: detects local anomalies by comparing a point's
    density to its neighbors. Catches users who are unusual for their
    peer group even if they look normal population-wide.

    SCALED — LOF uses Euclidean distance so all features must be on the
    same scale before fitting.

    Returns:
        predictions: array of 1 (normal) or -1 (anomaly)
        scores: negative outlier factor — more negative = more anomalous
    """
    print(f"\nTraining Local Outlier Factor (n_neighbors={CONFIG['lof_neighbors']}, "
          f"contamination={CONFIG['contamination']})...")

    if CONFIG['scale_for_lof']:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
    else:
        X_scaled = X.values

    model = LocalOutlierFactor(
        n_neighbors=CONFIG['lof_neighbors'],
        contamination=CONFIG['contamination'],
        novelty=False,          # transductive mode: score the training data itself
        n_jobs=-1
    )
    predictions = model.fit_predict(X_scaled)

    # negative_outlier_factor_: more negative = more anomalous (mirrors iso_score direction)
    scores = model.negative_outlier_factor_
    flagged = (predictions == -1).sum()
    print(f"  LOF flagged {flagged:,} rows ({flagged/len(X)*100:.2f}%)")
    return predictions, scores


# =============================================================================
# 3. SCORING
# =============================================================================

def build_continuous_risk_score(iso_scores, lof_scores, iso_preds, lof_preds):
    """
    Combines both models into a single continuous risk score from 0 to 1.
    Higher = more suspicious.

    Approach:
    1. Normalize each model's raw scores to [0, 1] independently.
       (Both models output "more negative = more anomalous" so we invert.)
    2. Average the two normalized scores.
    3. Apply a bonus multiplier when BOTH models agree a row is anomalous —
       consensus between two different detection methods is a stronger signal.

    The result is more informative than CRITICAL/WARNING/Low because you can
    rank suspects continuously rather than collapsing to three buckets.
    """
    def normalize(scores):
        mn, mx = scores.min(), scores.max()
        if mx == mn:
            return np.zeros_like(scores)
        # Invert: more negative raw score → higher risk score
        return 1 - (scores - mn) / (mx - mn)

    iso_norm = normalize(iso_scores)
    lof_norm = normalize(lof_scores)

    # Base score: average of both models
    combined = (iso_norm + lof_norm) / 2

    # Consensus bonus: when both models flag the same row, boost its score
    # by up to 15% of its current value. This rewards agreement without
    # hard-coding a categorical threshold.
    both_flagged = (iso_preds == -1) & (lof_preds == -1)
    combined[both_flagged] *= 1.15
    combined = np.clip(combined, 0, 1)

    return combined, iso_norm, lof_norm


# =============================================================================
# 4. USER-LEVEL AGGREGATION
# =============================================================================

def build_user_report(df):
    """
    Collapses the per-day output to one row per user.

    Why this matters: your actual output to a security analyst is
    "here are the 20 people most worth investigating" — not 1,650
    suspicious individual days. This aggregation answers that question.

    Columns:
    - risk_score_max:       worst single day's combined risk score
    - risk_score_mean:      average risk across all their days (chronic vs spike)
    - days_flagged_iso:     how many days IsolationForest flagged them
    - days_flagged_lof:     how many days LOF flagged them
    - days_flagged_both:    days BOTH models agreed — highest confidence signal
    - worst_iso_score:      raw iso score on their most anomalous day
    - peak_date:            the date of their worst day
    - job_search_days:      total days with job site activity
    - usb_days:             total days with USB activity (usb_count_zscore > 0)
    - after_hours_total:    sum of after-hours sessions across all days
    """
    agg = df.groupby('user').agg(
        risk_score_max=('combined_risk_score', 'max'),
        risk_score_mean=('combined_risk_score', 'mean'),
        days_flagged_iso=('iso_prediction', lambda x: (x == -1).sum()),
        days_flagged_lof=('lof_prediction', lambda x: (x == -1).sum()),
        days_flagged_both=('flagged_by_both', 'sum'),
        worst_iso_score=('iso_score', 'min'),           # most negative = worst
        after_hours_total=('after_hours_session_count', 'sum'),
    ).reset_index()

    # Find each user's peak risk date
    peak_dates = (
        df.loc[df.groupby('user')['combined_risk_score'].idxmax(), ['user', 'day']]
        .rename(columns={'day': 'peak_date'})
    )
    agg = agg.merge(peak_dates, on='user', how='left')

    # Job search days: days where job_site_visits_flag = 1
    if 'job_site_visits_flag' in df.columns:
        job_days = df[df['job_site_visits_flag'] == 1].groupby('user').size().reset_index(name='job_search_days')
        agg = agg.merge(job_days, on='user', how='left')
        agg['job_search_days'] = agg['job_search_days'].fillna(0).astype(int)

    # USB active days: days where usb_count_zscore is not NaN and > 0
    if 'usb_count_zscore' in df.columns:
        usb_days = df[df['usb_count_zscore'] > 0].groupby('user').size().reset_index(name='usb_days')
        agg = agg.merge(usb_days, on='user', how='left')
        agg['usb_days'] = agg['usb_days'].fillna(0).astype(int)

    # Sort by worst day score descending
    agg = agg.sort_values('risk_score_max', ascending=False).reset_index(drop=True)
    agg.index += 1  # rank starts at 1
    agg.index.name = 'rank'

    return agg


# =============================================================================
# 5. MAIN
# =============================================================================

def main():
    # Load
    df = load_data()
    X, feature_cols = prepare_features(df)

    # Models
    iso_preds, iso_scores = run_isolation_forest(X)
    lof_preds, lof_scores = run_lof(X)

    # Attach raw model outputs to df
    df['iso_prediction'] = iso_preds
    df['iso_score'] = iso_scores
    df['lof_prediction'] = lof_preds
    df['lof_score'] = lof_scores
    df['flagged_by_both'] = ((iso_preds == -1) & (lof_preds == -1)).astype(int)

    # Continuous risk score
    print("\nBuilding combined risk scores...")
    combined, iso_norm, lof_norm = build_continuous_risk_score(
        iso_scores, lof_scores, iso_preds, lof_preds
    )
    df['combined_risk_score'] = combined
    df['iso_score_norm'] = iso_norm
    df['lof_score_norm'] = lof_norm

    # Per-day output
    daily_path = os.path.join(CONFIG['base_path'], CONFIG['output_file_rows'])
    df.to_csv(daily_path, index=False)
    print(f"\nPer-day report saved to: {daily_path}")

    # Per-user output
    print("\nAggregating to user-level report...")
    user_report = build_user_report(df)
    user_path = os.path.join(CONFIG['base_path'], CONFIG['output_file_users'])
    user_report.to_csv(user_path)
    print(f"User-level report saved to: {user_path}")

    # Console summary
    total_flagged_days = df['flagged_by_both'].sum()
    users_with_any_flag = (
        (df[df['iso_prediction'] == -1]['user'].nunique()) +
        (df[df['lof_prediction'] == -1]['user'].nunique())
    ) // 2  # rough unique estimate

    print("\n" + "=" * 60)
    print("  TRAINING COMPLETE")
    print("=" * 60)
    print(f"  Days flagged by Isolation Forest: "
          f"{(iso_preds == -1).sum():,}")
    print(f"  Days flagged by LOF:              "
          f"{(lof_preds == -1).sum():,}")
    print(f"  Days flagged by BOTH (high conf): {total_flagged_days:,}")
    print("=" * 60)

    n = CONFIG['report_top_n']
    print(f"\nTOP {n} MOST SUSPICIOUS USERS:\n")
    report_cols = ['user', 'peak_date', 'risk_score_max', 'days_flagged_both',
                   'days_flagged_iso', 'days_flagged_lof', 'job_search_days',
                   'usb_days', 'after_hours_total']
    report_cols = [c for c in report_cols if c in user_report.columns]
    print(user_report[report_cols].head(n).to_string())


if __name__ == "__main__":
    main()