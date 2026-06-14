# COL-06: Validate session pairing logic (Logon/Logoff)

**Test Type:** Unit  
**Status:** PASS  

---

## Prerequisites

- Python 3.10+ installed
- `pandas` installed (`pip install pandas`)
- Run from the `dist/local` directory

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/local` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import the required modules and the internal processor function:
   ```python
   import pandas as pd
   from local_preprocessor import _compute_sessions
   ```
4. Define the mock configuration for session matching:
   ```python
   cfg = {
       'logon_activities': ['LOGON(STARTUP)', 'LOGON', 'WAKE'],
       'logoff_activities': ['LOGOFF', 'SLEEP', 'LOGOFF(shutdown)'],
       'work_start_hour': 8,
       'work_end_hour': 18,
       'weekend_days': [5, 6]
   }
   ```
5. Create a mock DataFrame to test that the session calculator works correctly in two scenarios:
   - **Scenario 1:** A normal, complete session (Logon -> Logoff).
   - **Scenario 2:** An incomplete session with no logoff, which should safely cap at midnight.
   ```python
   mock_events = pd.DataFrame([
       # Scenario 1: Normal session from 09:00 to 10:30 (90 minutes)
       {"user": "test", "timestamp": pd.Timestamp("2023-10-10 09:00:00"), "activity": "LOGON(STARTUP)"},
       {"user": "test", "timestamp": pd.Timestamp("2023-10-10 10:30:00"), "activity": "LOGOFF"},
       
       # (Injecting a shutdown event so the system knows the PC was turned off today)
       {"user": "test", "timestamp": pd.Timestamp("2023-10-10 11:00:00"), "activity": "LOGOFF(shutdown)"},

       # Scenario 2: Incomplete session starting at 23:00 with no logoff.
       # The logic should automatically cap this session at midnight (60 minutes).
       {"user": "test", "timestamp": pd.Timestamp("2023-10-10 23:00:00"), "activity": "LOGON"}
   ])
   ```
6. Process the mock dataframe through the session calculator:
   ```python
   results = _compute_sessions(mock_events, cfg)
   results = results.rename(columns={'logon_count': 'startup_count'})
   
   # Extract the specific row for our test day using .iloc
   output_row = results.iloc[0]
   print(f"Total active minutes: {output_row['total_active_minutes_day']}")
   print(f"Total startup count: {output_row['startup_count']}")
   ```

---

## Expected Output

The function pairs the 09:00 LOGON with the 10:30 LOGOFF (90 mins). 
For the 23:00 LOGON, because the day has a known shutdown state, the defensive session logic caps the open session at midnight (23:00 to 00:00 = 60 mins).
The total calculated active minutes for the day should equal exactly 150.0.

```
Total active minutes: 150.0
Total startup count: 1
```


---

## Actual Output


```python
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
...     # Scenario 1: Normal session from 09:00 to 10:30 (90 minutes)
...     {"user": "test", "timestamp": pd.Timestamp("2023-10-10 09:00:00"), "activity": "LOGON(STARTUP)"},
...     {"user": "test", "timestamp": pd.Timestamp("2023-10-10 10:30:00"), "activity": "LOGOFF"},
...     
...     # (Injecting a shutdown event so the system knows the PC was turned off today)
...     {"user": "test", "timestamp": pd.Timestamp("2023-10-10 11:00:00"), "activity": "LOGOFF(shutdown)"},
...
...     # Scenario 2: Incomplete session starting at 23:00 with no logoff.
...     # The logic should automatically cap this session at midnight (60 minutes).
...     {"user": "test", "timestamp": pd.Timestamp("2023-10-10 23:00:00"), "activity": "LOGON"}
... ])
>>> results = _compute_sessions(mock_events, cfg)
>>> results = results.rename(columns={'logon_count': 'startup_count'})
>>> 
>>> # Extract the specific row for our test day using .iloc
>>> output_row = results.iloc[0]
>>> print(f"Total active minutes: {output_row['total_active_minutes_day']}")
Total active minutes: 150.0
>>> print(f"Total startup count: {output_row['startup_count']}")
Total startup count: 1
```
