# COL-12: Test carryover days without a STARTUP event

**Test Type:** Integration  
**Status:** PASS  

---

## Prerequisites

- Python 3.10+ installed
- `pandas` installed (`pip install pandas`, `pip install numpy`)
- Run from the `dist/local` directory

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/local` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import the required modules and processor:
   ```python
   import numpy as np
   import pandas as pd
   from local_preprocessor import _compute_sessions
   ```
4. Define the configuration:
   ```python
   cfg = {
       'logon_activities': ['LOGON(STARTUP)', 'LOGON', 'WAKE'],
       'logoff_activities': ['LOGOFF', 'SLEEP', 'LOGOFF(shutdown)'],
       'work_start_hour': 8,
       'work_end_hour': 18,
       'weekend_days': [5, 6]
   }
   ```
5. Create a mock DataFrame simulating a "carryover" day where a user wakes/sleeps the machine but no STARTUP occurred (machine wasn't restarted):
   ```python
   mock_events = pd.DataFrame([
       {"user": "test_user", "timestamp": pd.Timestamp("2023-10-10 09:00:00"), "activity": "WAKE"},
       {"user": "test_user", "timestamp": pd.Timestamp("2023-10-10 11:00:00"), "activity": "SLEEP"},
       {"user": "test_user", "timestamp": pd.Timestamp("2023-10-10 13:00:00"), "activity": "LOGON"},
       {"user": "test_user", "timestamp": pd.Timestamp("2023-10-10 15:00:00"), "activity": "LOGOFF"}
   ])
   ```
6. Process the mock dataframe through the session calculator:
   ```python
   results = _compute_sessions(mock_events, cfg)
   output_row = results.iloc[0]
   
   print(f"Total active minutes: {output_row['total_active_minutes_day']}")
   print(f"Is NaN? {np.isnan(output_row['total_active_minutes_day'])}")
   ```

---

## Expected Output

Even though there was no `LOGON(STARTUP)` event in the data for that day, the session logic correctly handles the wake/sleep session boundaries and adds up the time spent actively logged in (2 hours + 2 hours = 4 hours, or 240.0 minutes). Active minutes are captured normally.

```
Total active minutes: 240.0
Is NaN? False
```

---

## Actual Output


```python
>>> import numpy as np
>>> import pandas as pd
>>> from local_preprocessor import _compute_sessions
>>> cfg = {
...     'logon_activities': ['LOGON(STARTUP)', 'LOGON', 'WAKE'],
...     'logoff_activities': ['LOGOFF', 'SLEEP', 'LOGOFF(shutdown)'],
...     'work_start_hour': 8,
...     'work_end_hour': 18,
...     'weekend_days': [5, 6]
... }
>>> mock_events = pd.DataFrame([
...     {"user": "test_user", "timestamp": pd.Timestamp("2023-10-10 09:00:00"), "activity": "WAKE"},
...     {"user": "test_user", "timestamp": pd.Timestamp("2023-10-10 11:00:00"), "activity": "SLEEP"},
...     {"user": "test_user", "timestamp": pd.Timestamp("2023-10-10 13:00:00"), "activity": "LOGON"},
...     {"user": "test_user", "timestamp": pd.Timestamp("2023-10-10 15:00:00"), "activity": "LOGOFF"}
... ])
>>> results = _compute_sessions(mock_events, cfg)
>>> output_row = results.iloc[0]
>>> 
>>> print(f"Total active minutes: {output_row['total_active_minutes_day']}")
Total active minutes: 240.0
>>> print(f"Is NaN? {np.isnan(output_row['total_active_minutes_day'])}")
Is NaN? False
```

