import pandas as pd
import numpy as np
import os
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler

# --- 1. CONFIGURATION ---
CONFIG = {
    # CHANGE THIS PATH to match your actual folder
    'base_path': r'F:\seniorpy',
    'input_file': 'model_intake_final.csv',
    'output_file': 'final_anomaly_report.csv',
    
    # "Contamination" is the % of users we expect to be malicious.
    # CERT r4.2 has about 2% malicious activity.
    'anomaly_rate': 0.02, 
    
    # Features to train the AI on
    'features': [
        'is_after_hours', 
        'total_usb_connections', 
        'job_site_visit', 
        'cloud_storage_visit', 
        'email_daily_z_score'
    ]
}

def load_data():
    path = os.path.join(CONFIG['base_path'], CONFIG['input_file'])
    print(f"Loading data from: {path}...")
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        print("CRITICAL ERROR: Input file not found. Run process_data.py first.")
        exit()

# --- 2. PREPARATION ---
df = load_data()

# Select only the numeric columns for the AI
X = df[CONFIG['features']]

# SCALE THE DATA
# AI models struggle if one number is small (0 or 1) and another is huge (1000).
# Scaling makes them all comparable.
print("Scaling data for One-Class SVM...")
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# --- 3. MODEL 1: ISOLATION FOREST ---
# Best for finding "Outliers" (mathematically distant points)
print(f"\nTraining Isolation Forest (Contamination: {CONFIG['anomaly_rate']})...")
iso_forest = IsolationForest(contamination=CONFIG['anomaly_rate'], n_estimators=100, random_state=42)

# -1 = Anomaly, 1 = Normal
df['iso_prediction'] = iso_forest.fit_predict(X) 
# The raw score (lower is worse)
df['iso_score'] = iso_forest.decision_function(X) 

# --- 4. MODEL 2: ONE-CLASS SVM ---
# Best for finding "Novelties" (new patterns never seen before)
print(f"Training One-Class SVM (This may take 30-60 seconds)...")
oc_svm = OneClassSVM(nu=CONFIG['anomaly_rate'], kernel='rbf', gamma='scale')

df['svm_prediction'] = oc_svm.fit_predict(X_scaled)

# --- 5. INTERPRETING RESULTS ---
# Convert Math (-1) to English ('YES')
df['is_anomaly_iso'] = df['iso_prediction'].apply(lambda x: 'YES' if x == -1 else 'No')
df['is_anomaly_svm'] = df['svm_prediction'].apply(lambda x: 'YES' if x == -1 else 'No')

# ENSEMBLE LOGIC (The "Risk Level")
# If BOTH models agree it's bad -> CRITICAL
# If only ONE model thinks it's bad -> WARNING
def calculate_risk(row):
    score = 0
    if row['iso_prediction'] == -1: score += 1
    if row['svm_prediction'] == -1: score += 1
    
    if score == 2: return 'CRITICAL'
    if score == 1: return 'WARNING'
    return 'Low'

df['risk_level'] = df.apply(calculate_risk, axis=1)

# --- 6. EXPORT & REPORT ---
# Save the full report for your Web UI
output_path = os.path.join(CONFIG['base_path'], CONFIG['output_file'])
df.to_csv(output_path, index=False)

# Filter for the console report
anomalies = df[df['risk_level'] != 'Low'].copy()
anomalies = anomalies.sort_values(by='iso_score', ascending=True) # Sort by "Worst Score"

print("-" * 60)
print(f"TRAINING COMPLETE.")
print(f"Results saved to: {output_path}")
print("-" * 60)
print(f"Total Rows Processed: {len(df)}")
print(f"Total Anomalies Detected: {len(anomalies)}")
print("-" * 60)
print("\nTOP 10 MOST SUSPICIOUS INSIDER THREATS:")
# Show readable columns
report_cols = ['user', 'date', 'risk_level', 'is_after_hours', 'total_usb_connections', 'email_daily_z_score', 'job_site_visit']
print(anomalies[report_cols].head(10).to_string(index=False))