import pandas as pd
import numpy as np
import os
from datetime import timedelta

# --- 1. CONFIGURATION ---
CONFIG = {
    # CHANGE THIS PATH to match your actual folder
    'base_path': r'F:\seniorpy',
    'output_file': 'model_intake_final.csv',
    
    # --- REGIONAL SETTINGS (Middle East / Sun-Thu Work Week) ---
    'apply_date_shift': True,  
    'shift_days': -1,          # Moves Mon -> Sun
    
    # Weekend Definition (Post-Shift)
    # 4=Fri, 5=Sat
    'weekend_days': [4, 5], 
    
    # --- WORKING HOURS (7 AM - 7 PM) ---
    # Captures 7:00 AM arrivals and up to 6:59 PM departures.
    'work_start_hour': 7,   # 07:00
    'work_end_hour': 19,    # 19:00 (7:00 PM)
    
    # --- DETECTION KEYWORDS ---
    'job_keywords': 'indeed|linkedin|monster|career|glassdoor|job',
    'cloud_keywords': 'dropbox|drive|mega|upload|box.com|mediafire|wetransfer'
}

def load_file(filename):
    path = os.path.join(CONFIG['base_path'], filename)
    print(f"Loading: {path}...")
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        print(f"\nCRITICAL ERROR: Could not find {filename}.")
        print(f"Please check that '{filename}' is inside '{CONFIG['base_path']}'")
        exit()

# --- 2. LOAD DATA ---
logon_df = load_file('logon.csv')
device_df = load_file('device.csv')
http_df = load_file('http.csv')
email_df = load_file('email.csv')

# --- 3. STANDARDIZE & SHIFT DATES ---
print("Standardizing and Shifting Dates...")
for df in [logon_df, device_df, http_df, email_df]:
    # Convert to datetime object
    df['date_dt'] = pd.to_datetime(df['date'], errors='coerce')
    
    # APPLY DATE SHIFT
    if CONFIG['apply_date_shift']:
        df['date_dt'] = df['date_dt'] + timedelta(days=CONFIG['shift_days'])
    
    # Create string representation
    df['day'] = df['date_dt'].dt.strftime('%m/%d/%Y')
    df['day_of_week'] = df['date_dt'].dt.dayofweek

if CONFIG['apply_date_shift']:
    print(f" > Data shifted by {CONFIG['shift_days']} day(s). Work week is now Sun-Thu.")

# --- 4. FEATURE ENGINEERING ---

# A. LOGON: After-Hours Logic
print(f"Processing Logon Data...")
print(f"  - Window: {CONFIG['work_start_hour']}:00 to {CONFIG['work_end_hour']}:00")
print(f"  - Weekends Flagged: Days {CONFIG['weekend_days']}")

def check_after_hours(row):
    if pd.isnull(row['date_dt']): return 0
    
    hour = row['date_dt'].hour
    dow = row['day_of_week']
    
    # 1. Check Time Window (Strict)
    # If hour is 19 (7PM), it is >= 19, so it gets FLAGGED.
    if hour < CONFIG['work_start_hour'] or hour >= CONFIG['work_end_hour']:
        return 1
    # 2. Check Weekend
    if dow in CONFIG['weekend_days']:
        return 1
    return 0

logon_df['after_hours_flag'] = logon_df.apply(check_after_hours, axis=1)
logon_feat = logon_df.groupby(['user', 'day'])['after_hours_flag'].max().reset_index()
logon_feat.rename(columns={'after_hours_flag': 'is_after_hours'}, inplace=True)

# B. DEVICE: USB Connections
print("Processing Device Data...")
usb_feat = device_df[device_df['activity'] == 'Connect'].groupby(['user', 'day']).size().reset_index(name='total_usb_connections')

# C. HTTP: Intent Detection
print("Processing HTTP Data...")
http_df['is_job'] = http_df['url'].str.contains(CONFIG['job_keywords'], case=False, na=False).astype(int)
http_df['is_cloud'] = http_df['url'].str.contains(CONFIG['cloud_keywords'], case=False, na=False).astype(int)

http_feat = http_df.groupby(['user', 'day']).agg(
    job_site_visit=('is_job', 'sum'),
    cloud_storage_visit=('is_cloud', 'sum')
).reset_index()

# D. EMAIL: Z-Score Calculation
print("Processing Email Data (Calculating Z-Scores)...")
email_daily = email_df.groupby(['user', 'day']).size().reset_index(name='email_count')
user_stats = email_daily.groupby('user')['email_count'].agg(['mean', 'std']).reset_index()
email_feat = email_daily.merge(user_stats, on='user', how='left')

email_feat['email_daily_z_score'] = (email_feat['email_count'] - email_feat['mean']) / email_feat['std']
email_feat['email_daily_z_score'] = email_feat['email_daily_z_score'].replace([np.inf, -np.inf], 0)
email_feat['email_daily_z_score'] = email_feat['email_daily_z_score'].fillna(0)

email_feat = email_feat[['user', 'day', 'email_daily_z_score']]

# --- 5. FINAL MERGE ---
print("Merging all datasets...")
final_df = logon_feat.merge(usb_feat, on=['user', 'day'], how='outer') \
                     .merge(http_feat, on=['user', 'day'], how='outer') \
                     .merge(email_feat, on=['user', 'day'], how='outer')

final_df = final_df.fillna(0)

# --- 6. EXPORT ---
final_df = final_df[['user', 'day', 'is_after_hours', 'total_usb_connections', 'job_site_visit', 'cloud_storage_visit', 'email_daily_z_score']]
final_df.rename(columns={'day': 'date'}, inplace=True)

output_path = os.path.join(CONFIG['base_path'], CONFIG['output_file'])
final_df.to_csv(output_path, index=False)

print("-" * 40)
print(f"SUCCESS! Preprocessing Complete.")
print(f"Output saved to: {output_path}")
print(f"Total Rows Generated: {len(final_df)}")
print("-" * 40)