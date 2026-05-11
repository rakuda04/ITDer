import pandas as pd
import numpy as np
import os
from datetime import timedelta

# --- 1. DYNAMIC PATH CALCULATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_PROJECT_PATH = SCRIPT_DIR  


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
        Standardizes dates and applies regional shifts (Sun-Thu week).

        FIX: The shift is applied BEFORE extracting day_of_week so that
        weekend_days in the config correctly refers to post-shift days.
        Previously, day_of_week was derived from the original date, meaning
        after-hours and weekend flags could be misaligned with the shifted date.
        """
        df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
        if self.config['apply_date_shift']:
            df['date_dt'] += timedelta(days=self.config['shift_days'])

        # all temporal features are derived from the SHIFTED date
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


        result = self._calculate_zscore(daily, 'user', 'logon_count', 'logon_count_zscore')
        # Drop raw logon_count — zscore and has_baseline capture its information.
        # Keeping the raw count would give the RF a redundant shortcut that
        # doesn't generalize: it learned the absolute count rather than deviation.
        return result.drop(columns=['logon_count'])

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
        

        daily = df.groupby(['user', 'day']).agg(
            job_site_visits=('is_job', 'sum'),
        ).reset_index()

        daily['job_site_visits_flag'] = (daily['job_site_visits'] > 0).astype(int)
       
        return daily.drop(columns=['job_site_visits'])

    def build_pipeline(self):
        logon_feat = self.process_logon()
        device_feat = self.process_device()
        http_feat = self.process_http()
        print("Merging Datasets...")
        final_df = (
            logon_feat
            .merge(device_feat, on=['user', 'day'], how='outer')
            .merge(http_feat,   on=['user', 'day'], how='outer')
        )

        final_df['date'] = pd.to_datetime(final_df['day'])
        final_df = final_df.sort_values(by=['user', 'date'])

        # Fill remaining numeric NaNs with 0 (counts, flags, etc.)
        # Z-score columns intentionally keep NaN to signal sparse baseline —
        zscore_cols = [c for c in final_df.columns if 'zscore' in c or 'z_score' in c]
        non_zscore_numeric = final_df.select_dtypes(include=[np.number]).columns.difference(zscore_cols)
        final_df[non_zscore_numeric] = final_df[non_zscore_numeric].fillna(0)

        # --- COMPOUND: Job search + USB in rolling 7-day window ---
        final_df.set_index('date', inplace=True)

        def compound_check(group):
            job_roll = group['job_site_visits_flag'].rolling('7D').max()
            usb_roll = group['usb_count_zscore'].rolling('7D').max()  # use zscore proxy
            return ((job_roll > 0) & (usb_roll > 0)).astype(int)

        final_df['job_search_plus_usb_week'] = final_df.groupby(
            'user', group_keys=False
        ).apply(compound_check)

        final_df.reset_index(inplace=True)



        output_path = os.path.normpath(
            os.path.join(self.config['base_path'], self.config['output_file'])
        )
        final_df.to_csv(output_path, index=False)
        print(f"SUCCESS! Shape: {final_df.shape} saved to {output_path}")
        return final_df


if __name__ == "__main__":
    CONFIG = {
        'base_path': BASE_PROJECT_PATH,
        'output_file': os.path.join('output', 'model_intake_final.csv'),
        'apply_date_shift': True,
        'shift_days': -1,           # Sun-Thu regional calendar correction
        'weekend_days': [4, 5],     # 4=Fri, 5=Sat in 0-indexed post-shift days
        'work_start_hour': 7,
        'work_end_hour': 19,
        'job_keywords': 'indeed|linkedin|monster|career|glassdoor|job',
        'min_baseline_days': 5,     # Minimum days of history before z-score is trusted
    }

    engineer = FeatureEngineer(CONFIG)
    engineer.build_pipeline()