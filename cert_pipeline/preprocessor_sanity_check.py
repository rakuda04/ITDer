"""
validate_output.py
------------------
Run this against model_intake_final.csv to verify the preprocessor
output is sane before feeding it into any anomaly detection model.

Usage:
    python validate_output.py
    python validate_output.py --path /custom/path/to/model_intake_final.csv
"""

import argparse
import os
import sys
import pandas as pd
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(os.path.dirname(SCRIPT_DIR), 'model_intake_final.csv')

ZSCORE_COLS = ['logon_count_zscore', 'usb_count_zscore', 'email_daily_z_score']
FLAG_COLS = [
    'weekend_session_flag',
    'usb_after_hours_flag', 'usb_on_weekend_flag',
    'job_site_visits_flag', 'upload_activity_flag',
    'job_search_plus_usb_week',
]

# after_hours_session_count is a count (2-13 is valid), not a binary flag
COUNT_COLS = ['after_hours_session_count', 'total_active_minutes_day',
              'usb_device_diversity_monthly']

PASS = "  ✅ PASS"
WARN = "  ⚠️  WARN"
FAIL = "  ❌ FAIL"


# ── Helpers ───────────────────────────────────────────────────────────────────
def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ── Checks ────────────────────────────────────────────────────────────────────
def check_shape(df):
    section("1. Shape & Schema")
    print(f"  Rows:    {len(df):,}")
    print(f"  Columns: {len(df.columns)}")
    print(f"  Users:   {df['user'].nunique():,}")

    rows_per_user = df.groupby('user').size()
    print(f"  Rows/user — min: {rows_per_user.min()}  "
          f"median: {rows_per_user.median():.0f}  "
          f"max: {rows_per_user.max()}")

    if rows_per_user.min() < 3:
        print(f"{WARN} Some users have < 3 rows. Z-scores for these will be 0 "
              "(std=0 fallback) — treat with caution in your model.")
    else:
        print(f"{PASS} All users have >= 3 rows.")

    missing_cols = [c for c in ZSCORE_COLS + FLAG_COLS if c not in df.columns]
    if missing_cols:
        print(f"{FAIL} Missing expected columns: {missing_cols}")
    else:
        print(f"{PASS} All expected feature columns present.")


def check_date_integrity(df):
    section("2. Date Integrity")
    parsed = pd.to_datetime(df['day'], errors='coerce')
    nat_count = parsed.isna().sum()

    if nat_count > 0:
        print(f"{FAIL} {nat_count:,} rows have unparseable dates in 'day' column.")
    else:
        print(f"{PASS} All dates parse correctly.")

    dow_counts = parsed.dt.dayofweek.value_counts().sort_index()
    dow_map = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun'}
    print("\n  Day-of-week distribution (should reflect your shift):")
    for d, n in dow_counts.items():
        print(f"    {dow_map[d]}: {n:,}")

    # With shift_days=-1 and weekend_days=[4,5], Sat/Sun should be near-zero
    sat = dow_counts.get(5, 0)
    sun = dow_counts.get(6, 0)
    total = len(df)
    sat_sun_pct = (sat + sun) / total * 100
    if sat_sun_pct > 0.05:
        print(f"  ℹ️  INFO {sat_sun_pct:.1f}% of rows fall on Sat/Sun. Two possible causes:")
        print(f"    (a) Your workforce genuinely works on those days — check if this matches reality.")
        print(f"    (b) Date shift misalignment — verify weekend_days config matches POST-shift days.")
    else:
        print(f"{PASS} Sat/Sun share is near-zero — consistent with a Sun-Thu work week after shift.")


def check_zscores(df):
    section("3. Z-Score Distributions")
    print("  Well-formed z-scores should have mean ~0 and std ~1.\n")

    for col in ZSCORE_COLS:
        if col not in df.columns:
            print(f"  {col}: MISSING\n")
            continue

        non_null = df[col].dropna()
        mean = non_null.mean()
        std  = non_null.std()
        p99  = non_null.quantile(0.99)
        zero_pct = (df[col] == 0).mean() * 100

        status = PASS
        notes  = []

        if abs(mean) > 0.5:
            status = WARN
            notes.append(f"mean={mean:.3f} is far from 0 — possible skew or groupby mismatch")
        if std < 0.5 or std > 2.0:
            status = WARN
            notes.append(f"std={std:.3f} outside expected [0.5, 2.0]")
        if zero_pct > 60:
            status = WARN
            notes.append(
                f"{zero_pct:.1f}% are exactly 0 — likely sparse users hitting the std=0 "
                "fallback. These rows look 'normal' to your model but have no real baseline."
            )

        print(f"  {col}:")
        print(f"    mean={mean:.3f}  std={std:.3f}  p99={p99:.2f}  zeros={zero_pct:.1f}%")
        print(f"  {status}" + (f" — {'; '.join(notes)}" if notes else ""))
        print()


def check_flags(df):
    section("4. Flag Column Sanity (should be 0 or 1 only)")
    for col in FLAG_COLS:
        if col not in df.columns:
            print(f"  {col}: MISSING")
            continue
        unique_vals = sorted(df[col].dropna().unique())
        bad = [v for v in unique_vals if v not in (0, 1, 0.0, 1.0)]
        rate = df[col].mean() * 100
        if bad:
            print(f"{FAIL} {col}: unexpected values {bad}")
        elif rate == 0:
            print(f"{WARN} {col}: always 0 — keyword regex may never match your data")
        elif rate > 80:
            print(f"{WARN} {col}: {rate:.1f}% are 1 — won't discriminate well")
        else:
            print(f"{PASS} {col}: {rate:.1f}% flagged")


def check_usb_days(df):
    section("5. days_since_last_usb Integrity")
    col = 'days_since_last_usb'
    if col not in df.columns:
        print(f"{FAIL} Column '{col}' not found.")
        return

    print(f"  Top 5 values:")
    print(df[col].value_counts().head(5).to_string())
    print()

    neg_count = (df[col] < 0).sum()
    if neg_count > 0:
        print(f"{FAIL} {neg_count:,} rows have NEGATIVE days_since_last_usb. "
              "Root cause: latest_usb_date includes a time component (e.g. 14:32:00) "
              "but date is midnight, so same-day USBs appear to be in the future. "
              "Fix: normalize latest_usb_date to midnight before subtracting.")
    else:
        print(f"{PASS} No negative values — date normalization is working correctly.")

    zero_pct = (df[col] == 0).mean() * 100
    if zero_pct > 50:
        print(f"{FAIL} {zero_pct:.1f}% of rows are 0. "
              "Users who never plugged in a USB look identical to users who used one today. "
              "Fix: use fillna(999) instead of fillna(0) for never-used-USB rows.")
    else:
        print(f"{PASS} Only {zero_pct:.1f}% of rows are 0 (same-day USB events).")

    # Add a check for after_hours_session_count as a count column
    if 'after_hours_session_count' in df.columns:
        section("4b. after_hours_session_count (count column, not a flag)")
        print(f"  This is correctly a count (0-N sessions). Distribution:")
        print(df['after_hours_session_count'].value_counts().sort_index().head(10).to_string())


def check_outer_merge_padding(df):
    section("6. Outer Merge Padding")
    print("  Rows where all feature columns are 0 are padded rows from the outer merge")
    print("  — the user had no activity from any source that day. Your model treats")
    print("  these identically to genuinely quiet active days.\n")

    feature_cols = [c for c in ZSCORE_COLS + FLAG_COLS + ['days_since_last_usb',
                    'total_active_minutes_day', 'usb_device_diversity_monthly']
                    if c in df.columns]

    all_zero = (df[feature_cols] == 0).all(axis=1)
    padded_pct = all_zero.mean() * 100

    if padded_pct > 50:
        print(f"{WARN} {padded_pct:.1f}% of rows are all-zero padded rows. "
              "This is common with CERT data but worth knowing — your model has no way "
              "to tell absence from quietness without an extra flag.")
    else:
        print(f"{PASS} {padded_pct:.1f}% of rows are all-zero — padding is not dominant.")


def check_constant_columns(df):
    section("7. Near-Constant Columns (> 95% one value)")
    numeric = df.select_dtypes(include=[np.number])
    found_any = False
    for col in numeric.columns:
        top_val_pct = numeric[col].value_counts(normalize=True).iloc[0]
        if top_val_pct > 0.95:
            dominant = numeric[col].value_counts().index[0]
            print(f"{WARN} {col}: {top_val_pct*100:.1f}% = {dominant} — low signal for anomaly detection")
            found_any = True
    if not found_any:
        print(f"{PASS} No near-constant columns found.")


def check_per_user_sample(df, n=3):
    section(f"8. Per-User Sample ({n} random users)")
    users = df['user'].dropna().unique()
    sample_users = np.random.choice(users, size=min(n, len(users)), replace=False)
    cols_to_show = ['day'] + [c for c in ZSCORE_COLS if c in df.columns][:2] + \
                   ['days_since_last_usb', 'job_site_visits_flag']
    cols_to_show = [c for c in cols_to_show if c in df.columns]
    for u in sample_users:
        sub = df[df['user'] == u]
        print(f"\n  User: {u}  |  {len(sub)} rows  |  "
              f"{sub['day'].min()} -> {sub['day'].max()}")
        print(sub[cols_to_show].head(6).to_string(index=False))


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Validate model_intake_final.csv")
    parser.add_argument('--path', default=DEFAULT_CSV, help='Path to CSV file')
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"\nFile not found: {args.path}")
        print("    Run the preprocessor first, or pass --path /your/path.csv")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  INSIDER THREAT PREPROCESSOR -- OUTPUT VALIDATION")
    print(f"  File: {args.path}")
    print(f"{'='*60}")

    df = pd.read_csv(args.path)

    check_shape(df)
    check_date_integrity(df)
    check_zscores(df)
    check_flags(df)
    check_usb_days(df)
    check_outer_merge_padding(df)
    check_constant_columns(df)
    check_per_user_sample(df)

    print(f"\n{'='*60}")
    print("  Validation complete. Review WARNs and FAILs above.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()