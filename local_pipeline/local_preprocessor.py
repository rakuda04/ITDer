# ============================================================
# local_preprocessor.py
#
# Reads activity_report.csv (produced by pipeline.py) and
# outputs a feature-engineered CSV matching the CERT schema:
#
#   date, user, day, total_active_minutes_day,
#   after_hours_session_count, weekend_session_flag,
#   logon_count_zscore, logon_count_zscore_has_baseline,
#   usb_count, usb_after_hours_flag, usb_on_weekend_flag,
#   usb_device_diversity_monthly,
#   usb_count_zscore, usb_count_zscore_has_baseline,
#   job_site_visits_flag, job_search_plus_usb_week
#
# KNOWN SCHEMA DIFFERENCES vs CERT preprocessor:
#   - usb_device_diversity_monthly: CERT measures nunique(pc) —
#     how many distinct machines a USB was plugged into (lateral
#     movement signal). Here we measure nunique(device_id) —
#     how many distinct USB devices were used that month.
#     These are different signals. CERT version needs auditing
#     before conclusions can be drawn across both datasets.
#
#   - total_active_minutes_day: not used by the current model
#     (confirmed). Carryover days (no STARTUP event) get NaN,
#     not 0, to avoid false "zero activity" signal if the
#     feature is re-introduced later.
# ============================================================

import sys
sys.dont_write_bytecode = True

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import timedelta

# ── config ───────────────────────────────────────────────────

# local_preprocessor.py lives in local_pipeline/
# input and output both go to local_pipeline/output/
SCRIPT_DIR = Path(__file__).resolve().parent / "output"

CONFIG = {
    'input_file':        SCRIPT_DIR / 'local_activity.csv',
    'output_file':       SCRIPT_DIR / 'local_model_intake.csv',
    'work_start_hour':   7,
    'work_end_hour':     19,
    'weekend_days':      [4, 5],       # 4=Fri, 5=Sat (regional Sun-Thu workweek)
    'job_keywords':      r'indeed|linkedin|monster|career|glassdoor|job',
    'min_baseline_days': 5,            # days of history before z-score is trusted

    # LOGON-type events: opening a session
    'logon_activities':  {'LOGON(STARTUP)', 'UNLOCK', 'WAKE'},
    # LOGOFF-type events: closing a session
    'logoff_activities': {'LOGOFF(shutdown)', 'LOCK', 'SLEEP'},
}

# ── helpers ──────────────────────────────────────────────────

def _is_after_hours(dt_series, start_hour, end_hour):
    return (
        (dt_series.dt.hour < start_hour) |
        (dt_series.dt.hour >= end_hour)
    ).astype(int)


def _is_weekend(dow_series, weekend_days):
    return dow_series.isin(weekend_days).astype(int)


def _calculate_zscore(df, user_col, value_col, new_col_name, min_baseline_days):
    """
    Per-user z-score. Mirrors CERT preprocessor logic exactly.
    Users with < min_baseline_days or std=0 get NaN + has_baseline=0.
    """
    stats = df.groupby(user_col)[value_col].agg(
        mean='mean', std='std', count='count'
    ).reset_index()

    merged = df.merge(stats, on=user_col, how='left')
    has_baseline = (merged['std'] > 0) & (merged['count'] >= min_baseline_days)

    merged[new_col_name] = np.where(
        has_baseline,
        (merged[value_col] - merged['mean']) / merged['std'],
        np.nan
    )
    merged[f'{new_col_name}_has_baseline'] = has_baseline.astype(int)

    return merged.drop(columns=['mean', 'std', 'count'])


# ── session calculation ──────────────────────────────────────

def _compute_sessions(df_security, cfg):
    """
    Walk security events chronologically per user per day.
    Pair LOGON-type → LOGOFF-type events into sessions.
    Duration is capped at midnight of the day the session started.

    Days with no LOGON(STARTUP) are carryover days (PC never rebooted).
    They still get a row but total_active_minutes_day = NaN.

    Returns a daily DataFrame with:
        user, day, total_active_minutes_day,
        after_hours_session_count, weekend_session_flag, logon_count
    """
    logon_acts  = cfg['logon_activities']
    logoff_acts = cfg['logoff_activities']
    start_h     = cfg['work_start_hour']
    end_h       = cfg['work_end_hour']
    weekend     = cfg['weekend_days']

    records = []

    for user, u_df in df_security.groupby('user'):
        u_df = u_df.sort_values('timestamp').reset_index(drop=True)

        # Get all calendar days that appear in this user's data
        all_days = u_df['timestamp'].dt.normalize().unique()

        for day_ts in sorted(all_days):
            day_str    = pd.Timestamp(day_ts).strftime('%m/%d/%Y')
            next_day   = day_ts + timedelta(days=1)
            has_startup = False

            # Events for this calendar day only
            day_mask = (u_df['timestamp'] >= day_ts) & (u_df['timestamp'] < next_day)
            day_events = u_df[day_mask].reset_index(drop=True)

            if day_events.empty:
                continue

            # Check if this day has a STARTUP event
            if 'LOGON(STARTUP)' in day_events['activity'].values:
                has_startup = True

            # ── session pairing state machine ────────────────
            total_minutes       = 0.0
            after_hours_count   = 0
            weekend_flag        = 0
            logon_count         = 0
            session_open_ts     = None
            session_open_after  = 0
            session_open_weekend= 0

            for _, ev in day_events.iterrows():
                act = ev['activity']
                ts  = ev['timestamp']

                if act in logon_acts:
                    # Only open a new session if none is currently open
                    if session_open_ts is None:
                        session_open_ts      = ts
                        session_open_after   = 1 if (ts.hour < start_h or ts.hour >= end_h) else 0
                        session_open_weekend = 1 if ts.dayofweek in weekend else 0
                        if act == 'LOGON(STARTUP)':
                            logon_count += 1

                elif act in logoff_acts:
                    if session_open_ts is not None:
                        # Cap session end at midnight
                        cap = min(ts, pd.Timestamp(next_day).tz_localize(ts.tzinfo)
                                  if ts.tzinfo else pd.Timestamp(next_day))
                        # Handle tz-aware timestamps
                        if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                            cap = min(ts, pd.Timestamp(next_day, tz=ts.tzinfo))
                        else:
                            cap = min(ts, pd.Timestamp(next_day))

                        duration = (cap - session_open_ts).total_seconds() / 60
                        total_minutes     += max(duration, 0)
                        after_hours_count += session_open_after
                        weekend_flag       = max(weekend_flag, session_open_weekend)
                        session_open_ts    = None

            # Unclosed session at end of day:
            # If the day has a SHUTDOWN event, the session genuinely ended
            # before we processed it — cap at midnight.
            # If no SHUTDOWN (data cutoff or script ran mid-day), we don't
            # know when the session ended — mark total as NaN, not a fake count.
            has_shutdown = any(
                ev['activity'] in logoff_acts and 'shutdown' in ev['activity'].lower()
                for _, ev in day_events.iterrows()
            )
            if session_open_ts is not None:
                if has_shutdown:
                    # Shouldn't normally happen (SHUTDOWN should have closed it),
                    # but cap at midnight defensively
                    if hasattr(session_open_ts, 'tzinfo') and session_open_ts.tzinfo is not None:
                        midnight = pd.Timestamp(next_day, tz=session_open_ts.tzinfo)
                    else:
                        midnight = pd.Timestamp(next_day)
                    duration = (midnight - session_open_ts).total_seconds() / 60
                    total_minutes     += max(duration, 0)
                    after_hours_count += session_open_after
                    weekend_flag       = max(weekend_flag, session_open_weekend)
                else:
                    # No shutdown found — data was cut off mid-session.
                    # total_active_minutes_day = NaN (unknown, not zero).
                    total_minutes = np.nan

            records.append({
                'user':                    user,
                'day':                     day_str,
                # NaN for carryover days (no STARTUP) or cut-off days (no SHUTDOWN)
                'total_active_minutes_day': total_minutes if has_startup else np.nan,
                'after_hours_session_count': after_hours_count,
                'weekend_session_flag':     weekend_flag,
                'logon_count':              logon_count,
            })

    return pd.DataFrame(records)


# ── processors ───────────────────────────────────────────────

def process_logon(df, cfg):
    print("[local_preprocessor] Processing session/logon features...")

    security = df[df['source'].isin(['Security', 'System'])].copy()
    security['timestamp'] = pd.to_datetime(security['timestamp'], utc=True).dt.tz_convert(None)
    security['activity']  = security['activity'].fillna('')

    daily = _compute_sessions(security, cfg)

    if daily.empty:
        return daily

    result = _calculate_zscore(
        daily, 'user', 'logon_count', 'logon_count_zscore',
        cfg['min_baseline_days']
    )
    return result.drop(columns=['logon_count'])


def process_device(df, cfg):
    print("[local_preprocessor] Processing USB/device features...")

    usb = df[
        (df['source'] == 'UMDF') &
        (df['category'] == 'CONNECT')
    ].copy()

    if usb.empty:
        print("  [!] No USB CONNECT events found.")
        return pd.DataFrame(columns=[
            'user', 'day', 'usb_count', 'usb_after_hours_flag',
            'usb_on_weekend_flag', 'usb_device_diversity_monthly',
            'usb_count_zscore', 'usb_count_zscore_has_baseline'
        ])

    usb['timestamp']   = pd.to_datetime(usb['timestamp'], utc=True).dt.tz_convert(None)
    usb['day']         = usb['timestamp'].dt.strftime('%m/%d/%Y')
    usb['day_of_week'] = usb['timestamp'].dt.dayofweek
    usb['month']       = usb['timestamp'].dt.to_period('M')

    usb['usb_after_hours'] = _is_after_hours(usb['timestamp'], cfg['work_start_hour'], cfg['work_end_hour'])
    usb['usb_weekend']     = _is_weekend(usb['day_of_week'], cfg['weekend_days'])

    daily = usb.groupby(['user', 'day']).agg(
        usb_count=('device', 'count'),
        usb_after_hours_flag=('usb_after_hours', 'max'),
        usb_on_weekend_flag=('usb_weekend', 'max'),
    ).reset_index()

    # DIFFERS FROM CERT: CERT measures nunique(pc) = distinct machines
    # (lateral movement). Here: nunique(device) = distinct USB devices
    # used that month. Pending audit of CERT version before aligning.
    monthly_diversity = usb.groupby(['user', 'month'])['device'].nunique().reset_index(
        name='usb_device_diversity_monthly'
    )
    daily['month'] = pd.to_datetime(daily['day']).dt.to_period('M')
    daily = daily.merge(monthly_diversity, on=['user', 'month'], how='left').drop(columns=['month'])

    return _calculate_zscore(daily, 'user', 'usb_count', 'usb_count_zscore', cfg['min_baseline_days'])


def process_browser(df, cfg):
    print("[local_preprocessor] Processing browser/HTTP features...")

    browser = df[df['source'] == 'Browser'].copy()

    if browser.empty:
        print("  [!] No browser events found.")
        return pd.DataFrame(columns=['user', 'day', 'job_site_visits_flag'])

    browser['timestamp'] = pd.to_datetime(browser['timestamp'], utc=True).dt.tz_convert(None)
    browser['day']       = browser['timestamp'].dt.strftime('%m/%d/%Y')
    browser['url']       = browser['url'].fillna('')

    browser['is_job'] = browser['url'].str.contains(
        cfg['job_keywords'], case=False, na=False
    ).astype(int)

    daily = browser.groupby(['user', 'day']).agg(
        job_site_visits=('is_job', 'sum')
    ).reset_index()

    daily['job_site_visits_flag'] = (daily['job_site_visits'] > 0).astype(int)
    return daily.drop(columns=['job_site_visits'])


# ── pipeline ─────────────────────────────────────────────────

def build_pipeline(cfg):
    # ── load ─────────────────────────────────────────────────
    input_path = cfg['input_file']
    print(f"[local_preprocessor] Loading {input_path}...")
    if not Path(input_path).exists():
        raise FileNotFoundError(f"CRITICAL: Could not find {input_path}")

    df = pd.read_csv(input_path)
    print(f"  → {len(df)} raw rows loaded")

    # ── process each source ──────────────────────────────────
    logon_feat   = process_logon(df, cfg)
    device_feat  = process_device(df, cfg)
    browser_feat = process_browser(df, cfg)

    # ── merge ────────────────────────────────────────────────
    print("[local_preprocessor] Merging features...")
    final_df = (
        logon_feat
        .merge(device_feat,  on=['user', 'day'], how='outer')
        .merge(browser_feat, on=['user', 'day'], how='outer')
    )

    final_df['date'] = pd.to_datetime(final_df['day'], format='%m/%d/%Y')
    final_df = final_df.sort_values(by=['user', 'date'])

    # ── drop empty days ──────────────────────────────────────
    # Days where no data was collected appear as empty shells after the
    # outer merge — typically the Windows Security event log has rolled
    # over and has no events for that period, but browser history from
    # the same date range pulled in a row anchor via the merge.
    # A day with no logon events, no USB events, and no browser activity
    # is not a "normal" day — it is a missing day. Keeping it would
    # inflate the day count and drag down mean-based aggregations.
    # We define "empty" as: no logon data (after_hours_session_count is NaN)
    # AND no USB activity (usb_count is NaN or 0)
    # AND no browser activity (job_site_visits_flag is NaN or 0).
    has_logon   = final_df['after_hours_session_count'].notna() & (final_df['after_hours_session_count'] > 0)
    has_logon_z = final_df['logon_count_zscore'].notna()
    has_usb     = final_df['usb_count'].notna() & (final_df['usb_count'] > 0)
    has_browser = final_df['job_site_visits_flag'].notna() & (final_df['job_site_visits_flag'] > 0)

    has_any_data = has_logon | has_logon_z | has_usb | has_browser
    n_before = len(final_df)
    final_df = final_df[has_any_data].copy()
    n_dropped = n_before - len(final_df)
    if n_dropped > 0:
        print(f"  [!] Dropped {n_dropped} empty days with no collected data")

    # ── fill NaNs ────────────────────────────────────────────
    # Z-score and total_active_minutes_day columns keep NaN intentionally.
    # Everything else (counts, flags) fills to 0.
    preserve_nan_cols = [c for c in final_df.columns if 'zscore' in c or 'z_score' in c]
    preserve_nan_cols.append('total_active_minutes_day')

    non_preserve = final_df.select_dtypes(include=[np.number]).columns.difference(preserve_nan_cols)
    final_df[non_preserve] = final_df[non_preserve].fillna(0)

    # ── compound feature ─────────────────────────────────────
    # job_search_plus_usb_week: within any rolling 7-day window,
    # did the user visit a job site AND connect a USB device?
    # Uses usb_count (not zscore) since zscore may be NaN early on.
    # Ensure columns exist even if a source had no data
    if 'job_site_visits_flag' not in final_df.columns:
        final_df['job_site_visits_flag'] = 0
    if 'usb_count' not in final_df.columns:
        final_df['usb_count'] = 0

    final_df = final_df.set_index('date').sort_index()

    # Compute rolling 7-day max per user for each signal separately,
    # then combine — avoids apply() DataFrame/Series ambiguity entirely.
    final_df['_job_roll'] = (
        final_df.groupby('user')['job_site_visits_flag']
        .transform(lambda x: x.rolling('7D').max())
    )
    final_df['_usb_roll'] = (
        final_df.groupby('user')['usb_count']
        .transform(lambda x: x.rolling('7D').max())
    )
    final_df['job_search_plus_usb_week'] = (
        (final_df['_job_roll'] > 0) & (final_df['_usb_roll'] > 0)
    ).astype(int)
    final_df = final_df.drop(columns=['_job_roll', '_usb_roll'])

    final_df = final_df.reset_index()

    # ── enforce schema column order ──────────────────────────
    schema_cols = [
        'date', 'user', 'day',
        'total_active_minutes_day',
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
    # Add any missing columns as NaN (defensive — shouldn't happen)
    for col in schema_cols:
        if col not in final_df.columns:
            print(f"  [!] Missing expected column '{col}' — filling with NaN")
            final_df[col] = np.nan

    final_df = final_df[schema_cols]

    # ── save ─────────────────────────────────────────────────
    output_path = cfg['output_file']
    final_df.to_csv(output_path, index=False)
    print(f"[local_preprocessor] ✅ Shape: {final_df.shape} → saved to {output_path}")
    return final_df


if __name__ == "__main__":
    build_pipeline(CONFIG)