# ING-03: Validate API data typing safety

**Test Type:** Unit  
**Status:** PASS  

---

## Prerequisites

- Python 3.10+ installed
- Run from the `dist/server` directory

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/server` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import the safe-casting internal functions from the API:
   ```python
   from ingest_api import _safe_int, _safe_float, _safe_date
   ```
4. Feed valid, invalid, and null data into the integer cast function to verify it safely handles bad inputs:
   ```python
   print(f"Valid float to int: {_safe_int(4.5)}")
   print(f"String float to int: {_safe_int('4.5')}")
   print(f"Empty string to int: {_safe_int('')}")
   print(f"Garbage string to int: {_safe_int('not-a-number')}")
   print(f"None to int: {_safe_int(None)}")
   ```
5. Do the same for the float and date cast functions:
   ```python
   print(f"\nGarbage string to float: {_safe_float('NaN_string')}")
   print(f"Empty string to date: {_safe_date('   ')}")
   print(f"Bad date string: {_safe_date('not-a-date')}")
   ```

---

## Expected Output

Because raw endpoint CSV data can be messy (e.g., pandas generating "NaN" strings or leaving cells empty), the database insertion layer uses these wrapper functions to sanitize types. Valid numbers cast correctly, while all garbage data safely collapses to Python `None` (which correctly translates to an SQL `NULL`), preventing Postgres from throwing a `data type mismatch` crash.

```
Valid float to int: 4
String float to int: 4
Empty string to int: None
Garbage string to int: None
None to int: None

Garbage string to float: None
Empty string to date: None
Bad date string: None
```


## Actual Output


```python
>>> from ingest_api import _safe_int, _safe_float, _safe_date
>>> print(f"Valid float to int: {_safe_int(4.5)}")
Valid float to int: 4
>>> print(f"String float to int: {_safe_int('4.5')}")
String float to int: 4
>>> print(f"Empty string to int: {_safe_int('')}")
Empty string to int: None
>>> print(f"Garbage string to int: {_safe_int('not-a-number')}")
Garbage string to int: None
>>> print(f"None to int: {_safe_int(None)}")
None to int: None
>>> print(f"\nGarbage string to float: {_safe_float('NaN_string')}")

Garbage string to float: None
>>> print(f"Empty string to date: {_safe_date('   ')}")
Empty string to date: None
>>> print(f"Bad date string: {_safe_date('not-a-date')}")
Bad date string: None
```

