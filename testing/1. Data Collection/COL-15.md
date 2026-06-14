# COL-15: Verify after-hours and weekend flag assignment

**Test Type:** Integration  
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
3. Import the required modules and the internal helper functions:
   ```python
   import pandas as pd
   from local_preprocessor import _is_after_hours, _is_weekend
   ```
4. Create a Pandas Series of timestamps representing different times and days:
   ```python
   # 2023-10-10 is a Tuesday. 2023-10-14 is a Saturday.
   timestamps = pd.Series(pd.to_datetime([
       "2023-10-10 10:00:00",  # Normal workday (Tuesday 10 AM)
       "2023-10-10 20:00:00",  # After hours (Tuesday 8 PM)
       "2023-10-14 14:00:00"   # Weekend (Saturday 2 PM)
   ]))
   ```
5. Apply the `_is_after_hours` check (using standard 07:00-19:00 boundary):
   ```python
   after_hours_flags = _is_after_hours(timestamps, start_hour=7, end_hour=19)
   print("After Hours Flags:", after_hours_flags.tolist())
   ```
6. Apply the `_is_weekend` check (using standard 4=Fri, 5=Sat logic configured in the system):
   ```python
   day_of_week = timestamps.dt.dayofweek
   weekend_flags = _is_weekend(day_of_week, weekend_days=[4, 5])
   print("Weekend Flags:", weekend_flags.tolist())
   ```

---

## Expected Output

The functions should correctly classify the timestamps.
- Tuesday 10 AM is NOT after hours (0) and NOT a weekend (0).
- Tuesday 8 PM IS after hours (1) and NOT a weekend (0).
- Saturday 2 PM is NOT after hours (0) but IS a weekend (1).

```
After Hours Flags: [0, 1, 0]
Weekend Flags: [0, 0, 1]
```

---

## Actual Output


```python
>>> import pandas as pd
>>> from local_preprocessor import _is_after_hours, _is_weekend
>>> # 2023-10-10 is a Tuesday. 2023-10-14 is a Saturday.
>>> timestamps = pd.Series(pd.to_datetime([
...     "2023-10-10 10:00:00",  # Normal workday (Tuesday 10 AM)
...     "2023-10-10 20:00:00",  # After hours (Tuesday 8 PM)
...     "2023-10-14 14:00:00"   # Weekend (Saturday 2 PM)
... ]))
>>> after_hours_flags = _is_after_hours(timestamps, start_hour=7, end_hour=19)
>>> print("After Hours Flags:", after_hours_flags.tolist())
After Hours Flags: [0, 1, 0]
>>> day_of_week = timestamps.dt.dayofweek
>>> weekend_flags = _is_weekend(day_of_week, weekend_days=[4, 5])
>>> print("Weekend Flags:", weekend_flags.tolist())
Weekend Flags: [0, 0, 1]
```


