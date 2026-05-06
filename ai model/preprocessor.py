import pandas as pd
import numpy as np
import os
from datetime import timedelta

# --- 1. DYNAMIC PATH CALCULATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_PROJECT_PATH = os.path.dirname(SCRIPT_DIR)

# Sentinel value for "never used USB" — high enough to look anomalous to models
USB_NEVER_USED_SENTINEL = 999


class FeatureEngineer:
    def __init__(self, config):
        self.config = config
        self.base_path = config['base_path']

    def load_file(self, filename):
        """Loads a CSV safely."""
        path = os.path.join(self.base_path, filename)
        print(f"Loading: {path}...")
        if not os.path.exists(path):
            raise FileNotFoundError(f"CRITICAL: Could not find {filename} in {self.base_path}")
        return pd.read_csv(path)

    def _apply_date_shift(self, df):
        """
        Standardizes dates and applies regional shifts (e.g., Sun-Thu week).

        FIX: The shift is applied BEFORE extracting day_of_week so that
        weekend_days in the config correctly refers to post-shift days.
        Previously, day_of_week was derived from the original date, meaning
        after-hours and weekend flags could be misaligned with the shifted date.
        """
        df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
        if self.config['apply_date_shift']:
            df['date_dt'] += timedelta(days=self.config['shift_days'])

        # All temporal features are derived from the SHIFTED date
        df['day'] = df['date_dt'].dt.strftime('%m/%d/%Y')
        df['day_of_week'] = df['date_dt'].dt.dayofweek
        df['month'] = df['date_dt'].dt.to_period('M')
        return df

    def _calculate_zscore(self, df, user_col, value_col, new_col_name):
        """
        Reusable helper to calculate per-user Z-Scores for any metric.

        FIX: Two separate problems solved here:

        Problem 1 — zero collision:
            The original code fell back to 0 when std=0 (sparse user).
            But 0 is also a valid z-score meaning "perfectly average day".
            A sparse user with 0 and an active user with 0 looked identical
            to any downstream model.

        Problem 2 — NaN also collides:
            Replacing 0 with NaN doesn't fully solve it either, because
            after the outer merge + fillna(0), those NaNs become 0 anyway.

        Solution:
            - Compute the real z-score for users with a valid baseline (std > 0,
              count >= min_baseline_days). These get their true float value.
            - Sparse/no-baseline users get NaN in the z-score column.
            - A companion binary column `*_has_baseline` (1/0) is added so the
              model always has an unambiguous signal about data quality.
            - In build_pipeline, z-score columns are explicitly excluded from
              the final fillna(0) sweep so NaN is preserved into the output.
              Your model's imputation step should handle these deliberately
              (e.g. fill with 0 only after using has_baseline as a feature).
        """
        MIN_BASELINE_DAYS = self.config.get('min_baseline_days', 5)

        stats = df.groupby(user_col)[value_col].agg(
            mean='mean',
            std='std',
            count='count'
        ).reset_index()

        merged = df.merge(stats, on=user_col, how='left')

        has_baseline = (merged['std'] > 0) & (merged['count'] >= MIN_BASELINE_DAYS)

        merged[new_col_name] = np.where(
            has_baseline,
            (merged[value_col] - merged['mean']) / merged['std'],
            np.nan  # Preserved through to output — NOT swept by fillna(0) in build_pipeline
        )

        # 1 = "this z-score is trustworthy", 0 = "sparse user, treat score as unknown"
        merged[f'{new_col_name}_has_baseline'] = has_baseline.astype(int)

        return merged.drop(columns=['mean', 'std', 'count'])

    def process_logon(self):
        # FIX: Added missing print statement; fixed double-indentation of method body
        print("Processing Logon Data...")
        df = self._apply_date_shift(self.load_file('dataset/logon.csv'))

        df['is_after_hours'] = (
            (df['date_dt'].dt.hour < self.config['work_start_hour']) |
            (df['date_dt'].dt.hour >= self.config['work_end_hour'])
        ).astype(int)
        df['is_weekend'] = df['day_of_week'].isin(self.config['weekend_days']).astype(int)

        df = df.sort_values(['user', 'date_dt'])

        df['next_activity'] = df.groupby('user')['activity'].shift(-1)
        df['next_time'] = df.groupby('user')['date_dt'].shift(-1)

        mask = (df['activity'] == 'Logon') & (df['next_activity'] == 'Logoff')
        df['session_duration'] = np.where(
            mask,
            (df['next_time'] - df['date_dt']).dt.total_seconds() / 60,
            0
        )

        daily = df.groupby(['user', 'day']).agg(
            total_active_minutes_day=('session_duration', 'sum'),
            after_hours_session_count=('is_after_hours', 'sum'),
            weekend_session_flag=('is_weekend', 'max'),
            logon_count=('activity', lambda x: (x == 'Logon').sum())
        ).reset_index()

        # FIX: Add is_active_day flag BEFORE the outer merge so we can
        # distinguish "user present, zero anomalies" from "user absent entirely"
        daily['is_active_day'] = 1

        return self._calculate_zscore(daily, 'user', 'logon_count', 'logon_count_zscore')

    def process_device(self):
        print("Processing USB/Device Data...")
        df = self._apply_date_shift(self.load_file('dataset/device.csv'))
        usb_only = df[df['activity'] == 'Connect'].copy()

        usb_only['usb_after_hours'] = (
            (usb_only['date_dt'].dt.hour < self.config['work_start_hour']) |
            (usb_only['date_dt'].dt.hour >= self.config['work_end_hour'])
        ).astype(int)
        usb_only['usb_weekend'] = usb_only['day_of_week'].isin(self.config['weekend_days']).astype(int)

        daily = usb_only.groupby(['user', 'day']).agg(
            usb_count=('activity', 'count'),
            usb_after_hours_flag=('usb_after_hours', 'max'),
            usb_on_weekend_flag=('usb_weekend', 'max'),
            latest_usb_date=('date_dt', 'max')
        ).reset_index()

        monthly_diversity = usb_only.groupby(['user', 'month'])['pc'].nunique().reset_index(
            name='usb_device_diversity_monthly'
        )
        daily['month'] = pd.to_datetime(daily['day']).dt.to_period('M')
        daily = daily.merge(monthly_diversity, on=['user', 'month'], how='left').drop(columns=['month'])

        return self._calculate_zscore(daily, 'user', 'usb_count', 'usb_count_zscore')

    def process_http(self):
        print("Processing HTTP Data...")
        df = self._apply_date_shift(self.load_file('dataset/http.csv'))

        df['is_job'] = df['url'].str.contains(
            self.config['job_keywords'], case=False, na=False
        ).astype(int)
        df['is_upload'] = df['url'].str.contains(
            self.config['cloud_keywords'], case=False, na=False
        ).astype(int)

        daily = df.groupby(['user', 'day']).agg(
            job_site_visits=('is_job', 'sum'),
            upload_activity=('is_upload', 'sum')
        ).reset_index()

        daily['job_site_visits_flag'] = (daily['job_site_visits'] > 0).astype(int)
        daily['upload_activity_flag'] = (daily['upload_activity'] > 0).astype(int)
        return daily.drop(columns=['job_site_visits', 'upload_activity'])

    def process_email(self):
        print("Processing Email Data...")
        df = self._apply_date_shift(self.load_file('dataset/email.csv'))
        daily = df.groupby(['user', 'day']).size().reset_index(name='email_count')
        return self._calculate_zscore(daily, 'user', 'email_count', 'email_daily_z_score')

    def build_pipeline(self):
        logon_feat = self.process_logon()
        device_feat = self.process_device()
        http_feat = self.process_http()
        email_feat = self.process_email()

        print("Merging Datasets...")
        final_df = (
            logon_feat
            .merge(device_feat, on=['user', 'day'], how='outer')
            .merge(http_feat,   on=['user', 'day'], how='outer')
            .merge(email_feat,  on=['user', 'day'], how='outer')
        )

        final_df['date'] = pd.to_datetime(final_df['day'])
        final_df = final_df.sort_values(by=['user', 'date'])

        # --- DAYS SINCE LAST USB ---
        # FIX: Strip the time component from latest_usb_date before subtracting.
        #
        # Root cause of -1 values: latest_usb_date is a full datetime
        # (e.g. 2010-01-03 14:32:00) but final_df['date'] is midnight
        # (2010-01-03 00:00:00). After ffill, a USB event from later that
        # same day appeared to be 14 hours in the future, giving dt.days = -1.
        #
        # Normalizing to date-only (midnight) before subtraction means
        # "USB happened sometime today" correctly gives days_since = 0.
        final_df['latest_usb_date'] = pd.to_datetime(
            final_df['latest_usb_date']
        ).dt.normalize()  # floors to midnight, kills the time component

        final_df['last_usb_date'] = final_df.groupby('user')['latest_usb_date'].ffill()

        final_df['days_since_last_usb'] = (
            final_df['date'] - final_df['last_usb_date']
        ).dt.days

        # FIX: Use sentinel (999) instead of 0 for "never used USB".
        # 0 means "used USB today" — filling with 0 makes never-users look
        # like constant USB users, which is the opposite of reality.
        final_df['days_since_last_usb'] = final_df['days_since_last_usb'].fillna(
            USB_NEVER_USED_SENTINEL
        )

        # FIX: is_active_day comes from logon presence before fillna(0).
        # After fillna(0), a non-logon day and an absent day look identical.
        # This flag lets models distinguish "present and quiet" from "absent".
        final_df['is_active_day'] = final_df['is_active_day'].fillna(0).astype(int)

        # Fill remaining numeric NaNs with 0 (counts, flags, etc.)
        # Z-score columns intentionally keep NaN to signal sparse baseline —
        # handle these in your model's imputation step, not here.
        zscore_cols = [c for c in final_df.columns if 'zscore' in c or 'z_score' in c]
        non_zscore_numeric = final_df.select_dtypes(include=[np.number]).columns.difference(zscore_cols)
        final_df[non_zscore_numeric] = final_df[non_zscore_numeric].fillna(0)

        # --- COMPOUND: Job search + USB in rolling 7-day window ---
        final_df.set_index('date', inplace=True)

        def compound_check(group):
            job_roll = group['job_site_visits_flag'].rolling('7D').max()
            usb_roll = group['usb_count_zscore'].rolling('7D').max()  # use zscore proxy
            return ((job_roll > 0) & (usb_roll > 0)).astype(int)

        # FIX: usb_count was dropped before this point in original code.
        # Now using usb_count_zscore as the signal (non-zero = USB occurred).
        # If you need raw usb_count in the rolling window, don't drop it above.
        final_df['job_search_plus_usb_week'] = final_df.groupby(
            'user', group_keys=False
        ).apply(compound_check)

        final_df.reset_index(inplace=True)

        # --- COMPOUND: Triple signal — job search + USB + cloud upload same day ---
        # Global, population-level feature — no per-user history needed.
        # Safe to use when deploying a CERT-trained model to local data.
        #
        # Rationale: each signal alone is noisy (job sites ~49% of days,
        # uploads ~34%). All three converging on the same day is rare and
        # specifically matches "preparing to leave": researching jobs while
        # simultaneously exfiltrating via USB and cloud upload.
        #
        # Unlike after_hours_total (which just flags consistent night owls),
        # this requires behavioral convergence across three independent channels.
        final_df['triple_signal_day'] = (
            (final_df['job_site_visits_flag'] == 1) &
            (final_df['usb_count_zscore'].fillna(0) > 0) &
            (final_df['upload_activity_flag'] == 1)
        ).astype(int)

        # Rolling 7-day version: did all three happen within the same week?
        # Catches cases where exfiltration is spread across a few days
        # rather than concentrated on one day.
        final_df.set_index('date', inplace=True)

        def triple_week_check(group):
            job_roll    = group['job_site_visits_flag'].rolling('7D').max()
            usb_roll    = group['usb_count_zscore'].fillna(0).rolling('7D').max()
            upload_roll = group['upload_activity_flag'].rolling('7D').max()
            return ((job_roll > 0) & (usb_roll > 0) & (upload_roll > 0)).astype(int)

        final_df['triple_signal_week'] = final_df.groupby(
            'user', group_keys=False
        ).apply(triple_week_check)

        final_df.reset_index(inplace=True)

        # Cleanup intermediate columns
        cols_to_drop = ['latest_usb_date', 'last_usb_date', 'logon_count', 'email_count']
        final_df = final_df.drop(columns=[c for c in cols_to_drop if c in final_df.columns])

        output_path = os.path.normpath(
            os.path.join(self.config['base_path'], self.config['output_file'])
        )
        final_df.to_csv(output_path, index=False)
        print(f"SUCCESS! Shape: {final_df.shape} saved to {output_path}")
        return final_df


# --- EXECUTION ---
if __name__ == "__main__":
    CONFIG = {
        'base_path': BASE_PROJECT_PATH,
        'output_file': 'model_intake_final.csv',
        'apply_date_shift': True,
        'shift_days': -1,           # Sun-Thu regional calendar correction
        'weekend_days': [4, 5],     # 4=Fri, 5=Sat in 0-indexed post-shift days
        'work_start_hour': 7,
        'work_end_hour': 19,
        'job_keywords': 'indeed|linkedin|monster|career|glassdoor|job',
        'cloud_keywords': 'dropbox|drive|mega|upload|box.com|mediafire|wetransfer',
        'min_baseline_days': 5,     # Minimum days of history before z-score is trusted
    }

    engineer = FeatureEngineer(CONFIG)
    engineer.build_pipeline()
    