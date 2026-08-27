import pandas as pd
daily = pd.read_csv('local_pipeline/output/local_report_daily.csv')
print(daily.groupby(['user','is_synthetic'])['ee_prediction'].apply(lambda x: (x==-1).sum()).reset_index(name='ee_flags').to_string())