# ING-02: Validate API device registration and ingestion

**Test Type:** Unit  
**Status:** PASS  


---

## Prerequisites

- Python 3.10+ installed
- `flask` and `psycopg2-binary` 
- Run from the `dist/server` directory

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/server` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import the required modules and mock the database connection to test the API route independently of Postgres:
   ```python
   import unittest.mock as mock
   from ingest_api import app
   
   client = app.test_client()
   ```
4. Create a mock database connection and cursor that successfully returns a device ID and run ID:
   ```python
   mock_conn = mock.MagicMock()
   mock_cur = mock.MagicMock()
   mock_conn.cursor.return_value.__enter__.return_value = mock_cur
   
   # Mock _get_or_create_device returning device ID 100
   # Mock _open_run returning run ID 500
   mock_cur.fetchone.side_effect = [[100], [500]]
   ```
5. Patch the `_connect` function to inject our mock, then fire a valid payload at the API:
   ```python
   payload = {
       "hostname": "DESKTOP-TEST",
       "windows_version": "10.0.19045",
       "features": [{"user": "akemi", "date": "2023-10-10", "usb_count": 5}]
   }
   
   with mock.patch('ingest_api._connect', return_value=mock_conn):
       with mock.patch('ingest_api.execute_values'):
           response = client.post('/ingest', json=payload)
           print(f"Status: {response.status_code}")
           print(f"Response: {response.get_json()}")
   ```

---

## Expected Output

The API successfully routes the payload, registers the machine (or looks it up), opens a pipeline transaction, and returns an HTTP 200 OK containing the dynamically generated `run_id`.

```
Status: 200
Response: {'rows_inserted': 1, 'run_id': 500, 'status': 'ok'}
```


## Actual Output


```python
>>> import unittest.mock as mock
>>> from ingest_api import app
>>> 
>>> client = app.test_client()
>>> mock_conn = mock.MagicMock()
>>> mock_cur = mock.MagicMock()
>>> mock_conn.cursor.return_value.__enter__.return_value = mock_cur
>>> 
>>> # Mock _get_or_create_device returning device ID 100
>>> # Mock _open_run returning run ID 500
>>> mock_cur.fetchone.side_effect = [[100], [500]]
>>> payload = {
...     "hostname": "DESKTOP-TEST",
...     "windows_version": "10.0.19045",
...     "features": [{"user": "akemi", "date": "2023-10-10", "usb_count": 5}]
... }
>>> 
>>> with mock.patch('ingest_api._connect', return_value=mock_conn):
...     with mock.patch('ingest_api.execute_values'):
...         response = client.post('/ingest', json=payload)
...         print(f"Status: {response.status_code}")
...         print(f"Response: {response.get_json()}")
... 
Status: 200
Response: {'rows_inserted': 1, 'run_id': 500, 'status': 'ok'}
```

