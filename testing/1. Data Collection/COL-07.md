# COL-07: Test 7-day rolling compound feature generation

**Test Type:** Unit  
**Status:** PASS  


---

## Prerequisites

- Python 3.10+ installed
- `pandas` installed 
- Run from the `dist/local` directory

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/local` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import the required modules:
   ```python
   import pandas as pd
   ```
4. Replicate the 7-day rolling logic from `local_preprocessor.py` on a mock dataset:
   ```python
   # Mock 15 days of data for a user
   dates = pd.date_range(start="2023-10-01", periods=15, freq='D')
   
   final_df = pd.DataFrame({
       'date': dates,
       'user': 'test_user',
       'job_site_visits_flag': [0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0], # Day 2 and Day 10
       'usb_count':            [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]  # Day 7
   })
   
   # Emulate the processor's rolling window calculation
   final_df = final_df.set_index('date').sort_index()
   
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
   ```
5. Check the result specifically for Day 7, Day 10, and Day 15 (which is more than 7 days after the USB event):
   ```python
   print(f"Day 7 Flag: {final_df.loc['2023-10-07', 'job_search_plus_usb_week']}")
   print(f"Day 10 Flag: {final_df.loc['2023-10-10', 'job_search_plus_usb_week']}")
   print(f"Day 15 Flag: {final_df.loc['2023-10-15', 'job_search_plus_usb_week']}")
   ```

---

## Expected Output

- On **Day 7** (2023-10-07), the user inserts a USB (`usb_count=1`). Because they visited a job site on Day 2 (within the 7-day window Oct 1-7), the compound flag triggers (`1`).
- On **Day 10** (2023-10-10), the user visits a job site again. The last USB insertion was on Day 7, which is within the 7-day lookback window (Oct 4-10), so the flag triggers again (`1`).
- On **Day 15** (2023-10-15), the user is evaluated. The 7-day lookback window is Oct 9-15. The job site visit on Day 10 is inside the window, but the USB event from Day 7 has expired. Therefore, the flag correctly resets to `0`.

```
Day 7 Flag: 1
Day 10 Flag: 1
Day 15 Flag: 0
```

---

## Actual Output


```python
>>> import pandas as pd
>>> # Mock 15 days of data for a user
>>> dates = pd.date_range(start="2023-10-01", periods=15, freq='D')
>>> 
>>> final_df = pd.DataFrame({
...     'date': dates,
...     'user': 'test_user',
...     'job_site_visits_flag': [0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0], # Day 2 and Day 10
...     'usb_count':            [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]  # Day 7
... })
>>> 
>>> # Emulate the processor's rolling window calculation
>>> final_df = final_df.set_index('date').sort_index()
>>> 
>>> final_df['_job_roll'] = (
...     final_df.groupby('user')['job_site_visits_flag']
...     .transform(lambda x: x.rolling('7D').max())
... )
>>> final_df['_usb_roll'] = (
...     final_df.groupby('user')['usb_count']
...     .transform(lambda x: x.rolling('7D').max())
... )
>>> 
>>> final_df['job_search_plus_usb_week'] = (
...     (final_df['_job_roll'] > 0) & (final_df['_usb_roll'] > 0)
... ).astype(int)
>>> print(f"Day 7 Flag: {final_df.loc['2023-10-07', 'job_search_plus_usb_week']}")
Day 7 Flag: 1
>>> print(f"Day 10 Flag: {final_df.loc['2023-10-10', 'job_search_plus_usb_week']}")
Day 10 Flag: 1
>>> print(f"Day 15 Flag: {final_df.loc['2023-10-15', 'job_search_plus_usb_week']}")
Day 15 Flag: 0
```

