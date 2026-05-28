"""
------------------------------
Three-stage insider threat detection pipeline:

  Stage 1 — Supervised (Random Forest)
    Trained on CERT r4.2 labels with windowed day-level labeling.
    Learns the actual behavioral pattern of known insiders.
    Evaluated with stratified k-fold cross-validation for honest metrics.
    Saved to disk for local deployment without retraining.

  Stage 2 — Unsupervised (IsolationForest + Elliptic Envelope ensemble)
    No labels used. Catches behavioral deviations from population norms.
    Acts as a safety net for novel insider behavior that doesn't match
    known CERT patterns.

  Stage 3 — Combined scoring + SHAP explanations
    Merges both scores equally into a final risk rank.
    SHAP explains per-user WHY they were flagged — which features drove
    their score — so analysts can triage in seconds instead of hours.

Deployment note:
    Trained models are saved to disk. On local data with no labels,
    set DEPLOY_MODE=True — supervised model predicts from CERT weights,
    unsupervised rescores the new population. No retraining needed.
    Recalibrate thresholds once you have 30+ days of local clean data.

"""

import json
import os
import pickle
import warnings

import numpy as np
import pandas as pd
import shap
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

warnings.filterwarnings('ignore')

# =============================================================================
# PATHS & CONFIG
# =============================================================================

SCRIPT_DIR        = os.path.dirname(os.path.abspath(__file__))
BASE_PROJECT_PATH = SCRIPT_DIR  # cert_pipeline/ is the project root

CONFIG = {
    'base_path'        : BASE_PROJECT_PATH,
    'input_file'       : os.path.join('output', 'model_intake_final.csv'),
    'labels_file'      : os.path.join('dataset', 'answers', 'insiders.csv'),
    'cert_version'     : '4.2',           
    # Outputs
    
    'output_daily'     : os.path.join('output', 'anomaly_report_daily.csv'),
    'output_users'     : os.path.join('output', 'anomaly_report_users.csv'),
    'output_thresholds': os.path.join('output', 'cert_thresholds.json'),
    'model_dir'        : os.path.join('output', 'models'),  

    # Set True when running on local data with no labels
    'deploy_mode'      : False,


    # Identifiers — never used as model features
    'ignore_columns': [
        'user', 'date', 'day',
        'total_active_minutes_day',      # retained in CSV for reference, not a model feature
        'usb_count_zscore_has_baseline', # always 1, no discriminative signal
    ],

    # Unsupervised settings
    'contamination'    : 0.02,
    'lof_neighbors'    : 20,

    # Supervised settings
    'cv_folds'         : 5,       # stratified k-fold
    'rf_n_estimators'  : 300,
    'rf_max_depth'     : 5,       # shallower = better generalization to local data

    # Combined score weights (must sum to 1.0)
    'weight_supervised'  : 0.7,
    'weight_unsupervised': 0.3,

    # Report
    'report_top_n'       : 20,

    # SHAP: most anomalous days to explain per user
    'shap_days_per_user' : 3,
}


# =============================================================================
# 1. LOAD & PREPARE
# =============================================================================

def load_features():
    path = os.path.join(CONFIG['base_path'], CONFIG['input_file'])
    print(f"Loading features from: {path}...")
    if not os.path.exists(path):
        raise FileNotFoundError("Input file not found. Run preprocessor.py first.")
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['day'], format='%m/%d/%Y', errors='coerce')
    print(f"  Loaded {len(df):,} rows | {df['user'].nunique():,} users")
    return df


def load_labels(df):
    """
    Loads insider labels and creates day-level binary labels.

    Labels a row insider=1 ONLY if that user's day falls within their
    active insider window (start -> end), not their whole employment.

    Why windowed labeling matters:
        RKD0604 was an insider for 7 days out of ~346 in the dataset.
        Labeling all 346 rows as insider=1 would train the model on
        mostly normal behavior with an insider label — the classifier
        would learn nothing useful. Windowing fixes this.
    """
    labels_path = os.path.join(CONFIG['base_path'], CONFIG['labels_file'])
    print(f"\nLoading insider labels from: {labels_path}...")
    if not os.path.exists(labels_path):
        raise FileNotFoundError(f"Labels file not found at {labels_path}")

    raw = pd.read_csv(labels_path)
    raw = raw[raw['dataset'].astype(str) == CONFIG['cert_version']].copy()
    print(f"  Found {len(raw)} insider records for CERT r{CONFIG['cert_version']}")
    print(f"  Unique insiders: {raw['user'].nunique()}")

    raw['start'] = pd.to_datetime(raw['start'], errors='coerce')
    raw['end']   = pd.to_datetime(raw['end'],   errors='coerce')

    # Build set of (user, normalized_date) for all insider active days
    insider_days = set()
    for _, row in raw.iterrows():
        if pd.isna(row['start']) or pd.isna(row['end']):
            continue
        for d in pd.date_range(start=row['start'].normalize(),
                               end=row['end'].normalize(), freq='D'):
            insider_days.add((row['user'], d))

    print(f"  Insider-day records: {len(insider_days):,}")

    df['insider_label'] = df.apply(
        lambda r: 1 if (r['user'], r['date']) in insider_days else 0, axis=1
    )

    n_pos = df['insider_label'].sum()
    n_neg = (df['insider_label'] == 0).sum()
    print(f"  insider days: {n_pos:,} | normal days: {n_neg:,} "
          f"| ratio 1:{n_neg//max(n_pos,1)}")
    return df


def prepare_features(df):
    """
    Selects feature columns, excludes labels and identifiers,
    and fills NaN z-scores with 0 (safe because has_baseline
    companion columns already signal data quality to the model).
    """
    exclude      = set(CONFIG['ignore_columns']) | {'insider_label'}
    feature_cols = [c for c in df.columns if c not in exclude]
    X            = df[feature_cols].copy()

    zscore_cols = [c for c in X.columns if 'zscore' in c or 'z_score' in c]
    X[zscore_cols] = X[zscore_cols].fillna(0)

    remaining = X.isnull().sum()
    remaining = remaining[remaining > 0]
    if not remaining.empty:
        print(f"  WARNING: Unexpected NaNs filled with 0: {remaining.to_dict()}")
        X = X.fillna(0)

    print(f"\nFeatures in use ({len(feature_cols)}):")
    for col in feature_cols:
        print(f"  - {col}")

    return X, feature_cols


# =============================================================================
# 2. SUPERVISED — RANDOM FOREST
# =============================================================================

def run_supervised(X, df, feature_cols):
    """
    Single Random Forest classifier with user-level held-out evaluation.

    Final configuration (Run 5 — best honest result):
    - No days_since_last_usb: tried cap, max_features, dual RF — all worse.
    - No email features: not available in local deployment.
    - 70/30 supervised/unsupervised weighting.
    - Healthy feature distribution: logon 26%, job sites 16%, compound 8%.
    - User-level AUC 0.962, Precision@20 44% on completely unseen users.
    """
    print("\n" + "="*60)
    print("  STAGE 1: SUPERVISED — RANDOM FOREST")
    print("="*60)

    y              = df['insider_label'].values
    sample_weights = compute_sample_weight('balanced', y)

    rf = RandomForestClassifier(
        n_estimators     = CONFIG['rf_n_estimators'],
        max_depth        = CONFIG['rf_max_depth'],
        min_samples_leaf = 50,  # higher = less overfitting to noisy insider signals
        random_state     = 42,
        n_jobs           = -1,
        class_weight     = 'balanced',
        max_features     = None,
    )

    # ── USER-LEVEL HELD-OUT EVALUATION ──────────────────────────────────────
    print(f"\n  ══ USER-LEVEL HELD-OUT EVALUATION (honest deployment estimate) ══")
    print(f"  Splitting by USER — test users are completely unseen during training.")
    print(f"  Running 5 seeds and averaging to reduce noise.\n")

    all_users     = df['user'].unique()
    insider_users = set(df[df['insider_label'] > 0]['user'].unique())
    normal_users  = [u for u in all_users if u not in insider_users]
    insider_list  = list(insider_users)

    user_auc_scores       = []
    user_precision_scores = []

    for seed in range(5):
        rng = np.random.RandomState(seed)
        rng.shuffle(insider_list)
        rng.shuffle(normal_users)

        n_test_insiders = max(1, int(len(insider_list) * 0.2))
        n_test_normal   = int(len(normal_users) * 0.2)
        test_users  = set(insider_list[:n_test_insiders] + normal_users[:n_test_normal])
        train_users = set(all_users) - test_users

        train_mask = df['user'].isin(train_users)
        test_mask  = df['user'].isin(test_users)

        X_tr = X[train_mask].values
        y_tr = y[train_mask]
        X_te = X[test_mask].values
        y_te = y[test_mask]

        if y_tr.sum() == 0 or y_te.sum() == 0:
            continue

        sw_tr = compute_sample_weight('balanced', y_tr)

        rf_u = RandomForestClassifier(
            n_estimators=CONFIG['rf_n_estimators'], max_depth=CONFIG['rf_max_depth'],
            min_samples_leaf=10, random_state=seed, n_jobs=-1, class_weight='balanced'
        )
        rf_u.fit(X_tr, y_tr, sample_weight=sw_tr)
        te_proba = rf_u.predict_proba(X_te)[:, 1]

        try:
            auc = roc_auc_score(y_te, te_proba)
        except Exception:
            auc = 0.5
        user_auc_scores.append(auc)

        test_df_u = df[test_mask].copy()
        test_df_u['u_score'] = te_proba
        user_scores_u = test_df_u.groupby('user')['u_score'].max()
        top20_u = user_scores_u.nlargest(20).index.tolist()
        hits_u  = [u for u in top20_u if u in insider_users]
        prec_u  = len(hits_u) / 20
        user_precision_scores.append(prec_u)

        n_ins = sum(1 for u in test_users if u in insider_users)
        print(f"  Seed {seed}: test={len(test_users)} users ({n_ins} insiders) | "
              f"AUC={auc:.3f} | Precision@20={prec_u*100:.0f}% ({len(hits_u)}/20)")

    mean_auc  = np.mean(user_auc_scores)
    mean_prec = np.mean(user_precision_scores)
    std_prec  = np.std(user_precision_scores)

    print(f"\n  ── Average across 5 seeds ──")
    print(f"  ROC-AUC        : {mean_auc:.3f} ± {np.std(user_auc_scores):.3f}")
    print(f"  Precision @20  : {mean_prec*100:.1f}% ± {std_prec*100:.1f}%")
    print(f"  ← THIS is your honest estimate for new unseen users locally.")
    print(f"  ← If this is 30-60%, the model has learned real patterns.")
    print(f"  ← If this is near 5%, the model only memorized CERT users.")

    print(f"\nRunning {CONFIG['cv_folds']}-fold stratified cross-validation...")
    cv = StratifiedKFold(n_splits=CONFIG['cv_folds'], shuffle=True, random_state=42)
    cv_results = cross_validate(
        rf, X, y, cv=cv,
        scoring        = ['precision', 'recall', 'roc_auc', 'f1'],
        params         = {'sample_weight': sample_weights},
        return_train_score = False
    )

    print(f"\n  Cross-validation results (mean ± std):")
    for metric in ['precision', 'recall', 'f1', 'roc_auc']:
        vals = cv_results[f'test_{metric}']
        print(f"    {metric:<12}: {vals.mean():.3f} ± {vals.std():.3f}")
    print(f"\n  These are day-level metrics on CERT r{CONFIG['cert_version']}.")

    # Train final model on full data
    print(f"\nTraining final RF on full dataset...")
    rf.fit(X, y, sample_weight=sample_weights)
    supervised_scores = rf.predict_proba(X)[:, 1]
    print(f"  Rows with P(insider) > 0.5: {(supervised_scores > 0.5).sum():,}")

    importance = pd.Series(rf.feature_importances_, index=feature_cols
                           ).sort_values(ascending=False)
    print(f"\n  Top 10 features by RF importance:")
    for feat, imp in importance.head(10).items():
        bar = '█' * int(imp * 200)
        print(f"    {feat:<45} {imp:.4f}  {bar}")

    model_dir  = os.path.join(CONFIG['base_path'], CONFIG['model_dir'])
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, 'rf_supervised.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump({'model': rf, 'feature_cols': feature_cols}, f)
    print(f"\n  Model saved to: {model_path}")

    return rf, supervised_scores, cv_results



# =============================================================================
# 3. UNSUPERVISED — ISOFOREST + LOF
# =============================================================================

def run_isolation_forest(X):
    """Tree-based global outlier detection. NOT scaled."""
    print(f"\nTraining Isolation Forest (contamination={CONFIG['contamination']})...")
    model  = IsolationForest(contamination=CONFIG['contamination'],
                             n_estimators=200, random_state=42, n_jobs=-1)
    preds  = model.fit_predict(X)
    scores = model.decision_function(X)
    print(f"  Flagged {(preds==-1).sum():,} rows ({(preds==-1).mean()*100:.2f}%)")

    model_dir = os.path.join(CONFIG['base_path'], CONFIG['model_dir'])
    os.makedirs(model_dir, exist_ok=True)
    with open(os.path.join(model_dir, 'iso_forest.pkl'), 'wb') as f:
        pickle.dump(model, f)

    return model, preds, scores


def run_elliptic(X, X_normal):
    """
    Elliptic Envelope trained on CERT normal rows only.
    Learns the statistical boundary of normal behavior from 1,000 users
    over 18 months. At inference time, applied without refitting so the
    local population is judged against the same CERT normal baseline.
    Complements IsoForest: ISO finds global outliers, EE finds statistical
    deviations from normal behavior.
    """
    print(f"\nTraining Elliptic Envelope on normal rows only ({len(X_normal):,} rows)...")
    scaler   = StandardScaler()
    X_normal_scaled = scaler.fit_transform(X_normal)
    X_scaled = scaler.transform(X)

    model = EllipticEnvelope(
        contamination    = CONFIG['contamination'],
        random_state     = 42,
        support_fraction = 0.9,
    )
    model.fit(X_normal_scaled)
    preds  = model.predict(X_scaled)
    scores = model.score_samples(X_scaled)
    print(f"  Flagged {(preds==-1).sum():,} rows ({(preds==-1).mean()*100:.2f}%)")

    model_dir = os.path.join(CONFIG['base_path'], CONFIG['model_dir'])
    os.makedirs(model_dir, exist_ok=True)
    with open(os.path.join(model_dir, 'elliptic_env.pkl'), 'wb') as f:
        pickle.dump({'model': model, 'scaler': scaler}, f)
    print(f"  Saved to: {os.path.join(model_dir, 'elliptic_env.pkl')}")

    return preds, scores


def run_unsupervised(X, df):
    print("\n" + "="*60)
    print("  STAGE 2: UNSUPERVISED — ISOFOREST + ELLIPTIC ENVELOPE")
    print("="*60)
    iso_model, iso_preds, iso_scores = run_isolation_forest(X)
    # Train EE on normal rows only so it learns what normal looks like
    normal_mask = df["insider_label"] == 0
    X_normal    = X[normal_mask.values]
    lof_preds, lof_scores = run_elliptic(X, X_normal)
    return iso_model, iso_preds, iso_scores, lof_preds, lof_scores


# =============================================================================
# 4. COMBINED SCORING
# =============================================================================

def normalize_scores(scores, invert=True):
    mn, mx = scores.min(), scores.max()
    if mx == mn:
        return np.zeros_like(scores, dtype=float)
    norm = (scores - mn) / (mx - mn)
    return 1 - norm if invert else norm


def build_combined_score(supervised_scores, iso_scores, lof_scores,
                         iso_preds, lof_preds):
    """
    Merges supervised (RF probability) + unsupervised (IsoForest+LOF)
    into a single [0,1] risk score with equal weighting.

    Unsupervised consensus bonus: +15% when both IsoForest AND LOF
    flag the same row — agreement between two different detection
    methods is a stronger signal than either alone.
    """
    print("\n" + "="*60)
    print("  STAGE 3: COMBINED SCORING")
    print("="*60)

    iso_norm = normalize_scores(iso_scores, invert=True)
    lof_norm = normalize_scores(lof_scores, invert=True)

    both_flagged = (iso_preds == -1) & (lof_preds == -1)
    unsupervised = (iso_norm + lof_norm) / 2
    unsupervised[both_flagged] *= 1.15
    unsupervised = np.clip(unsupervised, 0, 1)

    combined = np.clip(
        CONFIG['weight_supervised']   * supervised_scores +
        CONFIG['weight_unsupervised'] * unsupervised,
        0, 1
    )

    print(f"  Weights: supervised={CONFIG['weight_supervised']:.0%}  "
          f"unsupervised={CONFIG['weight_unsupervised']:.0%}")
    print(f"  Combined — mean: {combined.mean():.3f}  "
          f"max: {combined.max():.3f}  p98: {np.percentile(combined, 98):.3f}")

    return combined, unsupervised, iso_norm, lof_norm


# =============================================================================
# 5. SHAP EXPLANATIONS
# =============================================================================

def build_shap_explanations(rf_model, X, df, feature_cols):
    """
    Computes SHAP values for the Random Forest on each user's most
    anomalous days. Uses TreeExplainer — exact and fast for tree models.

    Output per user-day looks like:
        BSS0369  03/15/2010  (risk=0.81)
          ▲ usb_count_zscore           +0.31  (drove score UP)
          ▲ job_site_visits_flag       +0.18
          ▲ triple_signal_week         +0.12
          ▼ logon_count_zscore         -0.04  (drove score DOWN)

    This tells the analyst exactly WHY someone was flagged so they can
    clear false positives in seconds rather than digging through raw logs.
    """
    print("\n" + "="*60)
    print("  SHAP EXPLANATIONS")
    print("="*60)

    explainer = shap.TreeExplainer(rf_model)

    n_days  = CONFIG['shap_days_per_user']
    top_idx = (
        df.groupby('user')['combined_risk_score']
        .nlargest(n_days)
        .reset_index(level=0)
        .index
    )

    X_explain = X.iloc[top_idx]
    print(f"  Computing SHAP for {len(X_explain):,} rows "
          f"({df['user'].nunique()} users × {n_days} days)...")

    sv = explainer.shap_values(X_explain)
    # shap return format changed across versions:
    # - older shap: list of 2 arrays [class0, class1], each shape (rows, features)
    # - newer shap: single array of shape (rows, features, classes)
    if isinstance(sv, list):
        sv = sv[1]           # older: take class 1 (insider)
    elif sv.ndim == 3:
        sv = sv[:, :, 1]     # newer: slice class 1 from last axis

    shap_df = pd.DataFrame(sv, columns=feature_cols, index=X_explain.index)
    shap_df['user']                = df.loc[X_explain.index, 'user'].values
    shap_df['day']                 = df.loc[X_explain.index, 'day'].values
    shap_df['combined_risk_score'] = df.loc[X_explain.index, 'combined_risk_score'].values
    shap_df['supervised_score']    = df.loc[X_explain.index, 'supervised_score'].values

    print(f"  Done.")
    return shap_df, explainer


def format_shap_for_report(shap_df, feature_cols, top_n_features=5):
    """Returns dict {user: explanation_string} for console/report output."""
    explanations = {}
    for user, group in shap_df.groupby('user'):
        lines = []
        for _, row in group.sort_values('combined_risk_score', ascending=False).iterrows():
            feat_shap = row[feature_cols].astype(float)
            top_feats = feat_shap.abs().nlargest(top_n_features)
            lines.append(f"  {row['day']}  (risk={row['combined_risk_score']:.3f})")
            for feat in top_feats.index:
                v = feat_shap[feat]
                lines.append(f"    {'▲' if v > 0 else '▼'} {feat:<42} {v:+.4f}")
        explanations[user] = '\n'.join(lines)
    return explanations


# =============================================================================
# 6. USER REPORT
# =============================================================================

def build_user_report(df, feature_cols):
    agg = df.groupby('user').agg(
        final_risk_score  =('combined_risk_score', 'max'),
        supervised_max    =('supervised_score',    'max'),
        supervised_mean   =('supervised_score',    'mean'),
        unsupervised_max  =('unsupervised_score',  'max'),
        days_flagged_iso  =('iso_prediction',      lambda x: (x == -1).sum()),
        days_flagged_lof  =('lof_prediction',      lambda x: (x == -1).sum()),
        days_flagged_both =('flagged_by_both',     'sum'),
        known_insider_days=('insider_label',       'sum'),
    ).reset_index()

    peak = (df.loc[df.groupby('user')['combined_risk_score'].idxmax(), ['user', 'day']]
              .rename(columns={'day': 'peak_date'}))
    agg  = agg.merge(peak, on='user', how='left')

    if 'job_site_visits_flag' in df.columns:
        j   = df[df['job_site_visits_flag']==1].groupby('user').size().reset_index(name='job_search_days')
        agg = agg.merge(j, on='user', how='left').fillna({'job_search_days': 0})
        agg['job_search_days'] = agg['job_search_days'].astype(int)

    if 'usb_count_zscore' in df.columns:
        u   = df[df['usb_count_zscore']>0].groupby('user').size().reset_index(name='usb_days')
        agg = agg.merge(u, on='user', how='left').fillna({'usb_days': 0})
        agg['usb_days'] = agg['usb_days'].astype(int)

    if 'triple_signal_week' in df.columns:
        t   = df[df['triple_signal_week']==1].groupby('user').size().reset_index(name='triple_signal_days')
        agg = agg.merge(t, on='user', how='left').fillna({'triple_signal_days': 0})
        agg['triple_signal_days'] = agg['triple_signal_days'].astype(int)

    agg = agg.sort_values('final_risk_score', ascending=False).reset_index(drop=True)
    agg.index += 1
    agg.index.name = 'rank'
    return agg


# =============================================================================
# 7. THRESHOLD EXPORT
# =============================================================================

def export_thresholds(combined, supervised_scores, iso_scores, lof_scores, df):
    """
    Saves CERT score percentiles and raw score ranges for use as deployment
    thresholds. The min/max ranges for IsoForest and LOF are saved so that
    inference.py can normalize local scores against the same CERT scale,
    preventing local min/max compression from inflating everyone's score.
    """
    thresholds = {
        'combined_risk_p99'    : float(np.percentile(combined,          99)),
        'combined_risk_p98'    : float(np.percentile(combined,          98)),
        'combined_risk_p95'    : float(np.percentile(combined,          95)),
        'supervised_p98'       : float(np.percentile(supervised_scores, 98)),
        'supervised_p95'       : float(np.percentile(supervised_scores, 95)),
        'iso_score_p98'        : float(np.percentile(iso_scores,         2)),
        'iso_score_p95'        : float(np.percentile(iso_scores,         5)),
        'lof_score_p98'        : float(np.percentile(lof_scores,         2)),
        # CERT score ranges — used by inference.py to normalize local scores
        # on the same scale as training, preventing population size compression.
        'iso_score_min'        : float(iso_scores.min()),
        'iso_score_max'        : float(iso_scores.max()),
        'lof_score_min'        : float(lof_scores.min()),
        'lof_score_max'        : float(lof_scores.max()),
        'contamination_used'   : CONFIG['contamination'],
        'training_rows'        : int(len(df)),
        'training_users'       : int(df['user'].nunique()),
        'cert_version'         : CONFIG['cert_version'],
        'recommended_threshold': float(np.percentile(combined,          98)),
    }

    path = os.path.join(CONFIG['base_path'], CONFIG['output_thresholds'])
    with open(path, 'w') as f:
        json.dump(thresholds, f, indent=2)

    print(f"\n  Saved to: {path}")
    print(f"  Recommended threshold (p98): {thresholds['recommended_threshold']:.4f}")
    print(f"  On local data: flag any user-day with combined_risk_score above this.")
    return thresholds


# =============================================================================
# 8. MAIN
# =============================================================================

def main():
    # Load
    df = load_features()
    if not CONFIG['deploy_mode']:
        df = load_labels(df)
    else:
        df['insider_label'] = 0
        print("\nDEPLOY MODE: No labels. Using saved CERT-trained models.")

    X, feature_cols = prepare_features(df)

    # Stage 1: Supervised
    if not CONFIG['deploy_mode']:
        rf_model, supervised_scores, cv_results = run_supervised(X, df, feature_cols)
    else:
        model_path = os.path.join(CONFIG['base_path'], CONFIG['model_dir'],
                                  'rf_supervised.pkl')
        print(f"\nDEPLOY MODE: Loading saved RF from {model_path}...")
        with open(model_path, 'rb') as f:
            saved = pickle.load(f)
        rf_model          = saved['model']
        supervised_scores = rf_model.predict_proba(X)[:, 1]

    # Stage 2: Unsupervised
    iso_model, iso_preds, iso_scores, lof_preds, lof_scores = run_unsupervised(X, df)

    # Stage 3: Combined
    combined, unsupervised, iso_norm, lof_norm = build_combined_score(
        supervised_scores, iso_scores, lof_scores, iso_preds, lof_preds
    )

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

    # SHAP
    shap_df, _        = build_shap_explanations(rf_model, X, df, feature_cols)
    shap_explanations = format_shap_for_report(shap_df, feature_cols)

    # Reports
    print("\nAggregating user-level report...")
    user_report = build_user_report(df, feature_cols)

    print("\n" + "="*60)
    print("  DEPLOYMENT THRESHOLDS")
    print("="*60)
    thresholds = export_thresholds(combined, supervised_scores,
                                   iso_scores, lof_scores, df)

    # Save
    daily_path = os.path.join(CONFIG['base_path'], CONFIG['output_daily'])
    user_path  = os.path.join(CONFIG['base_path'], CONFIG['output_users'])
    shap_path  = os.path.join(CONFIG['base_path'], 'output', 'shap_values.csv')

    df.to_csv(daily_path, index=False)
    user_report.to_csv(user_path)
    shap_df.to_csv(shap_path, index=False)

    print(f"\nOutputs saved:")
    print(f"  Per-day report  : {daily_path}")
    print(f"  User report     : {user_path}")
    print(f"  SHAP values     : {shap_path}")

    # Console summary
    print("\n" + "="*60)
    print("  RESULTS SUMMARY")
    print("="*60)
    if not CONFIG['deploy_mode']:
        print(f"\n  Supervised CV ({CONFIG['cv_folds']}-fold):")
        for m in ['precision', 'recall', 'f1', 'roc_auc']:
            v = cv_results[f'test_{m}']
            print(f"    {m:<12}: {v.mean():.3f} ± {v.std():.3f}")
    print(f"\n  Unsupervised:")
    print(f"    IsoForest flagged : {(iso_preds==-1).sum():,} days")
    print(f"    LOF flagged       : {(lof_preds==-1).sum():,} days")
    print(f"    Both agreed       : {df['flagged_by_both'].sum():,} days")

    n = CONFIG['report_top_n']
    print(f"\n{'='*60}")
    print(f"  TOP {n} USERS")
    print(f"{'='*60}")
    rcols = ['user', 'peak_date', 'final_risk_score', 'supervised_max',
             'days_flagged_both', 'job_search_days', 'usb_days',
             'triple_signal_days', 'known_insider_days']
    rcols = [c for c in rcols if c in user_report.columns]
    print(user_report[rcols].head(n).to_string())

    print(f"\n{'='*60}")
    print(f"  SHAP EXPLANATIONS — TOP 5 USERS")
    print(f"{'='*60}")
    for user in user_report['user'].head(5).tolist():
        rank  = user_report[user_report['user'] == user].index[0]
        score = user_report.loc[rank, 'final_risk_score']
        print(f"\n  Rank {rank} | {user} | risk={score:.3f}")
        print(shap_explanations.get(user, "  (no explanation available)"))


if __name__ == "__main__":
    main()