# ============================================================
# synthetic_generator.py
#
# Generates synthetic normal and insider users based on
# CERT r4.2 feature distributions for use as a background
# population during local inference.
#
# Purpose:
#   LOF and IsoForest need a meaningful population to score
#   against. With one local user, the neighborhood is too
#   small. Synthetic users from CERT distributions give the
#   unsupervised models a realistic baseline population.
#
# Insider scenarios (from CERT r4.2):
#   Scenario 1 — after-hours logon + USB connect, no prior USB
#   Scenario 2 — job site visits + USB spike above baseline
#   Scenario 3 — after-hours logon + USB connect (keylogger)
#
# Toggles:
#   PHASED         — True: normal phase then active threat phase
#                    False: consistently anomalous throughout
#   RANDOM_SCENARIOS — True: randomly assign scenarios to insiders
#                      False: one insider per scenario (always 3)
# ============================================================

import sys
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# ── paths ────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
CERT_INTAKE  = SCRIPT_DIR.parent / "cert_pipeline" / "output" / "model_intake_final.csv"
OUTPUT_PATH  = SCRIPT_DIR / "output" / "synthetic_population.csv"

# ── toggles ──────────────────────────────────────────────────
PHASED           = True    # True = normal phase → active phase; False = always anomalous
RANDOM_SCENARIOS = True    # True = random scenario per insider; False = one per scenario

# ── config ───────────────────────────────────────────────────
N_NORMAL_USERS  = 27       # synthetic normal users
N_INSIDER_USERS = 3        # synthetic insider users
N_DAYS          = 30       # days per synthetic user
NORMAL_PHASE_DAYS = 20     # days of clean behavior before going rogue (PHASED=True only)
RANDOM_SEED     = 42

SCENARIOS = [1, 2, 3]

# ── feature columns (must match schema) ──────────────────────
FEATURE_COLS = [
    'after_hours_session_count',
    'weekend_session_flag',
    'logon_count_zscore',
    'logon_count_zscore_has_baseline',
    'usb_count',
    'usb_after_hours_flag',
    'usb_on_weekend_flag',
    'usb_device_diversity_monthly',
    'usb_count_zscore',
    'usb_count_zscore_has_baseline',
    'job_site_visits_flag',
    'job_search_plus_usb_week',
]

# ── helpers ──────────────────────────────────────────────────

def _load_cert_distributions(path: Path) -> dict:
    """Extract per-feature mean and std from CERT intake CSV."""
    print(f"[synthetic] Loading CERT distributions from {path}...")
    if not path.exists():
        raise FileNotFoundError(f"CRITICAL: {path} not found. Run cert_preprocessor.py first.")

    df = pd.read_csv(path)

    # Only use normal (non-insider) rows for baseline distributions
    # if insider_label exists; otherwise use all rows
    if 'insider_label' in df.columns:
        df = df[df['insider_label'] == 0]

    stats = {}
    for col in FEATURE_COLS:
        if col not in df.columns:
            print(f"  [!] Column '{col}' not in CERT intake — using defaults")
            stats[col] = {'mean': 0.0, 'std': 0.1, 'min': 0.0, 'max': 1.0}
            continue
        stats[col] = {
            'mean': df[col].mean(),
            'std':  df[col].std(),
            'min':  df[col].min(),
            'max':  df[col].max(),
        }
    print(f"  → Distributions extracted for {len(stats)} features")
    return stats


def _generate_normal_day(stats: dict, rng: np.random.RandomState) -> dict:
    """Generate one day of normal behavior sampled from CERT distributions."""
    row = {}
    for col in FEATURE_COLS:
        s    = stats[col]
        val  = rng.normal(s['mean'], max(s['std'], 0.01))
        # Clip to observed CERT range
        val  = np.clip(val, s['min'], s['max'])

        # Binary flags should stay binary
        if col in ('weekend_session_flag', 'usb_after_hours_flag',
                   'usb_on_weekend_flag', 'job_site_visits_flag',
                   'job_search_plus_usb_week',
                   'logon_count_zscore_has_baseline',
                   'usb_count_zscore_has_baseline'):
            val = int(round(val))
            val = np.clip(val, 0, 1)

        # Count columns should be non-negative integers
        if col in ('after_hours_session_count', 'usb_count',
                   'usb_device_diversity_monthly'):
            val = max(0, int(round(val)))

        row[col] = val
    return row


def _generate_insider_day(stats: dict, scenario: int,
                           rng: np.random.RandomState) -> dict:
    """
    Generate one anomalous day for a given insider scenario.
    Starts from a normal day and applies scenario-specific overrides.
    """
    row = _generate_normal_day(stats, rng)

    if scenario == 1:
        # After-hours logon + USB connect, no prior USB history
        row['after_hours_session_count']  = int(rng.randint(2, 6))
        row['usb_count']                  = int(rng.randint(3, 8))
        row['usb_after_hours_flag']       = 1
        row['usb_count_zscore']           = float(rng.uniform(2.5, 4.5))
        row['usb_count_zscore_has_baseline'] = 1
        row['job_site_visits_flag']       = 0
        row['job_search_plus_usb_week']   = 0

    elif scenario == 2:
        # Job site visits + USB spike
        row['job_site_visits_flag']       = 1
        row['usb_count']                  = int(rng.randint(4, 10))
        row['usb_count_zscore']           = float(rng.uniform(2.0, 4.0))
        row['usb_count_zscore_has_baseline'] = 1
        row['job_search_plus_usb_week']   = 1
        row['after_hours_session_count']  = int(rng.randint(0, 2))

    elif scenario == 3:
        # After-hours logon + USB connect (keylogger transfer)
        row['after_hours_session_count']  = int(rng.randint(3, 7))
        row['usb_count']                  = int(rng.randint(2, 5))
        row['usb_after_hours_flag']       = 1
        row['usb_count_zscore']           = float(rng.uniform(1.5, 3.5))
        row['usb_count_zscore_has_baseline'] = 1
        row['weekend_session_flag']       = int(rng.randint(0, 2))
        row['job_site_visits_flag']       = 0

    return row


# ── generators ───────────────────────────────────────────────

def generate_normal_users(stats: dict, rng: np.random.RandomState) -> pd.DataFrame:
    """Generate N_NORMAL_USERS × N_DAYS rows of normal behavior."""
    print(f"[synthetic] Generating {N_NORMAL_USERS} normal users × {N_DAYS} days...")
    records = []
    base_date = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    for i in range(N_NORMAL_USERS):
        user = f"synth_normal_{i+1:03d}"
        for d in range(N_DAYS):
            day_dt = base_date - timedelta(days=N_DAYS - d)
            row    = _generate_normal_day(stats, rng)
            row.update({
                'user': user,
                'date': day_dt.strftime('%Y-%m-%d'),
                'day':  day_dt.strftime('%m/%d/%Y'),
                'total_active_minutes_day': float(rng.normal(480, 60)),
                'is_synthetic': 1,
                'insider_label': 0,
                'scenario': None,
            })
            records.append(row)

    return pd.DataFrame(records)


def generate_insider_users(stats: dict, rng: np.random.RandomState) -> pd.DataFrame:
    """
    Generate N_INSIDER_USERS with anomalous behavior.
    If PHASED=True: normal for first NORMAL_PHASE_DAYS, then rogue.
    If RANDOM_SCENARIOS=True: randomly assign scenario per insider.
    If RANDOM_SCENARIOS=False: one insider per scenario (ignores N_INSIDER_USERS).
    """
    n_users  = N_INSIDER_USERS if RANDOM_SCENARIOS else len(SCENARIOS)
    base_date = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    if RANDOM_SCENARIOS:
        scenario_assignments = [rng.choice(SCENARIOS) for _ in range(n_users)]
    else:
        scenario_assignments = SCENARIOS  # one per scenario

    print(f"[synthetic] Generating {n_users} insider users × {N_DAYS} days "
          f"(PHASED={PHASED}, RANDOM_SCENARIOS={RANDOM_SCENARIOS})...")
    for i, sc in enumerate(scenario_assignments):
        print(f"  insider_{i+1:03d} → Scenario {sc}")

    records = []
    for i, scenario in enumerate(scenario_assignments):
        user = f"synth_insider_{i+1:03d}"
        for d in range(N_DAYS):
            day_dt   = base_date - timedelta(days=N_DAYS - d)
            is_rogue = (not PHASED) or (d >= NORMAL_PHASE_DAYS)

            if is_rogue:
                row = _generate_insider_day(stats, scenario, rng)
            else:
                row = _generate_normal_day(stats, rng)

            row.update({
                'user':          user,
                'date':          day_dt.strftime('%Y-%m-%d'),
                'day':           day_dt.strftime('%m/%d/%Y'),
                'total_active_minutes_day': float(rng.normal(480, 60)),
                'is_synthetic':  1,
                'insider_label': 1 if is_rogue else 0,
                'scenario':      scenario,
            })
            records.append(row)

    return pd.DataFrame(records)


# ── main ─────────────────────────────────────────────────────

def generate(output_path: Path = OUTPUT_PATH) -> pd.DataFrame:
    rng   = np.random.RandomState(RANDOM_SEED)
    stats = _load_cert_distributions(CERT_INTAKE)

    normal_df  = generate_normal_users(stats, rng)
    insider_df = generate_insider_users(stats, rng)

    combined = pd.concat([normal_df, insider_df], ignore_index=True)
    combined  = combined.sort_values(['user', 'date']).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)

    print(f"\n[synthetic] ✅ {len(combined)} rows → {output_path}")
    print(f"  Normal users  : {N_NORMAL_USERS} × {N_DAYS} = {N_NORMAL_USERS * N_DAYS} rows")
    print(f"  Insider users : {len(insider_df['user'].unique())} × {N_DAYS} = {len(insider_df)} rows")
    return combined


if __name__ == "__main__":
    generate()