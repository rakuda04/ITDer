# COL-03: Verify date bounding parameter (`days`)

**Test Type:** Unit  
**Status:** PASS  

---

## Prerequisites

- Python 3.10+ installed
- Run from the `dist/local` directory

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/local` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import the required modules and collectors:
   ```python
   from datetime import datetime, timezone, timedelta
   from collectors.windows_events import get_security_events
   from collectors.browser_history import get_browser_history
   ```
4. Set the bounding parameter to a small window (e.g., 1 day) and fetch data:
   ```python
   test_days = 1
   cutoff = datetime.now(timezone.utc) - timedelta(days=test_days)
   
   security = get_security_events(days=test_days)
   history = get_browser_history(days=test_days)
   ```
5. Check if any events fall outside the requested time window (older than the cutoff):
   ```python
   out_of_bounds_sec = [e for e in security if e['timestamp'] < cutoff]
   out_of_bounds_hist = [e for e in history if e['timestamp'] < cutoff]
   
   print(f"Out of bounds Security events: {len(out_of_bounds_sec)}")
   print(f"Out of bounds Browser events: {len(out_of_bounds_hist)}")
   ```

---

## Expected Output

The `days` parameter is strictly enforced within the collector query logic. Step 5 should print `0` for both counts, meaning absolutely no timestamps older than the cutoff leaked through the query filters.

```
Out of bounds Security events: 0
Out of bounds Browser events: 0
```


---

## Actual Output


```python
>>> from datetime import datetime, timezone, timedelta
>>> from collectors.windows_events import get_security_events
>>> from collectors.browser_history import get_browser_history
>>> test_days = 1
>>> cutoff = datetime.now(timezone.utc) - timedelta(days=test_days)
>>> 
>>> security = get_security_events(days=test_days)
>>> history = get_browser_history(days=test_days)
>>> 
>>> out_of_bounds_sec = [e for e in security if e['timestamp'] < cutoff]
>>> out_of_bounds_hist = [e for e in history if e['timestamp'] < cutoff]
>>> 
>>> print(f"Out of bounds Security events: {len(out_of_bounds_sec)}")
Out of bounds Security events: 0
>>> print(f"Out of bounds Browser events: {len(out_of_bounds_hist)}")
Out of bounds Browser events: 0
```

