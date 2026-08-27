# COL-10: Validate output CSV generation

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
3. Import the required modules:
   ```python
   import csv
   import tempfile
   from datetime import datetime, timezone
   from data_collector import _export
   import config
   ```
4. Create a mock event to export:
   ```python
   mock_event = [{
       "timestamp": datetime.now(timezone.utc),
       "source": "UMDF",
       "event_id": 2003,
       "activity": "",
       "category": "CONNECT",
       "device": "USB\\VID",
       "user": "test_user",
       "logon_id": "",
       "browser": "",
       "url": "",
       "title": "",
       "visit_count": ""
   }]
   ```
5. Export to a temporary CSV file using the pipeline's logic:
   ```python
   with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
       temp_path = tmp.name
   
   _export(mock_event, temp_path)
   ```
6. Read the CSV back and verify the headers and timestamp format:
   ```python
   with open(temp_path, "r", encoding="utf-8") as f:
       reader = csv.DictReader(f)
       headers = reader.fieldnames
       row = next(reader)
   
   print(f"Headers match config? {headers == config.CSV_FIELDNAMES}")
   print(f"Total headers: {len(headers)}")
   print(f"Formatted timestamp: {row['timestamp']}")
   ```

---

## Expected Output

The `_export` function must use the strictly defined `config.CSV_FIELDNAMES` array to enforce the column order, ignoring missing keys. It should also successfully serialize the timezone-aware `datetime` object into a string.

```
[pipeline] [OK] Saved 1 records -> C:\Users\...\Temp\tmpXXXX.csv
Headers match config? True
Total headers: 12
Formatted timestamp: 2023-10-10 14:30:00.123456+0000
```





## Actual Output


```python
>>> import csv
>>> import tempfile
>>> from datetime import datetime, timezone
>>> from data_collector import _export
>>> import config
>>> mock_event = [{
...     "timestamp": datetime.now(timezone.utc),
...     "source": "UMDF",
...     "event_id": 2003,
...     "activity": "",
...     "category": "CONNECT",
...     "device": "USB\\VID",
...     "user": "test_user",
...     "logon_id": "",
...     "browser": "",
...     "url": "",
...     "title": "",
...     "visit_count": ""
... }]
>>> with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
...     temp_path = tmp.name
... 
>>> _export(mock_event, temp_path)
[pipeline] [OK] Saved 1 records -> C:\Users\user\AppData\Local\Temp\tmpgraqodc1.csv
>>> with open(temp_path, "r", encoding="utf-8") as f:
...     reader = csv.DictReader(f)
...     headers = reader.fieldnames
...     row = next(reader)
... 
>>> print(f"Headers match config? {headers == config.CSV_FIELDNAMES}")
Headers match config? True
>>> print(f"Total headers: {len(headers)}")
Total headers: 12
>>> print(f"Formatted timestamp: {row['timestamp']}")
Formatted timestamp: 2026-06-13 10:58:31.189404+0000
```


