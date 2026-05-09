import os
import pandas as pd

# 1. Setup the path (Same logic as before)
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.abspath(os.path.join(script_dir, "..", "dataset", "answers", "insiders.csv"))

def get_r42_insider_data(target_path):
    try:
        # Load the dataset
        df = pd.read_csv(target_path)

        # 2. Filter for only r4.2
        # Note: We check for both string '4.2' and float 4.2 to be safe
        df_filtered = df[df['dataset'].astype(str) == '4.2'].copy()

        # 3. Get unique usernames from the filtered data
        insider_usernames = df_filtered['user'].unique().tolist()
        total_insiders = len(insider_usernames)

        # Output results
        print(f"--- Insider Details (Filtered: r4.2) ---")
        if df_filtered.empty:
            print("No rows found for dataset 4.2. Check the 'dataset' column values.")
        else:
            print(df_filtered[['dataset', 'scenario', 'details', 'user', 'start', 'end']].head())
        
        print("\n--- Summary ---")
        print(f"Total number of r4.2 insiders: {total_insiders}")
        print(f"Usernames Array: {insider_usernames}")

        return insider_usernames

    except FileNotFoundError:
        print(f"Error: File not found at {target_path}")
    except KeyError as e:
        print(f"Error: Missing column {e}")

if __name__ == "__main__":
    get_r42_insider_data(csv_path) 