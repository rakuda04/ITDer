# ING-05: Validate transaction error handling (`pipeline_runs`)

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
3. We will mock the database layer to simulate a hard crash occurring midway through a data insertion loop. Import the required modules:
   ```python
   import unittest.mock as mock
   from ingest_api import app
   client = app.test_client()
   ```
4. Set up the mocks. We allow device registration (`_get_or_create_device`) and run tracking (`_open_run`) to succeed, but force `_insert_features` to throw a fatal error:
   ```python
   mock_conn = mock.MagicMock()
   mock_cur = mock.MagicMock()
   mock_conn.cursor.return_value.__enter__.return_value = mock_cur
   
   # Setup return values for device creation and run generation
   mock_cur.fetchone.side_effect = [[100], [500]]
   
   # Set up the mock for the close_run function to capture what the API tries to do
   mock_close_run = mock.MagicMock()
   ```
5. Apply the mocks, fire a payload, and verify that the `except` block successfully executed `_close_run` with the "failed" status so the dashboard knows the run aborted. We will temporarily suppress the server's standard error output so that the terminal only shows what the Client receives:
   ```python
   payload = {"hostname": "CRASH-TEST", "features": [{"user": "user"}]}
   
   import sys, io
   stderr_backup = sys.stderr
   sys.stderr = io.StringIO() # Suppress server traceback
   
   with mock.patch('ingest_api._connect', return_value=mock_conn):
       with mock.patch('ingest_api._insert_features', side_effect=Exception("Simulated Database Crash")):
           with mock.patch('ingest_api._close_run', mock_close_run):
               response = client.post('/ingest', json=payload)
               sys.stderr = stderr_backup # Restore stderr
               
               print(f"HTTP Status: {response.status_code}")
               print(f"Error caught by API: {response.get_json()['error']}")
               
               # The arguments passed to _close_run in the except block
               args, kwargs = mock_close_run.call_args
               print(f"Run ID closed: {args[1]}")
               print(f"Status saved to DB: {args[2]}")
               print(f"Error saved to DB: {kwargs.get('error', '')}")
   ```

---

## Expected Output

The API correctly detects the internal failure, aborts the insert process, and updates the `pipeline_runs` table so the run isn't permanently stuck in a "running" state. The client gracefully receives a 500 error and a clean JSON message, with no ugly tracebacks visible on their end.

```
HTTP Status: 500
Error caught by API: Simulated Database Crash
Run ID closed: 500
Status saved to DB: failed
Error saved to DB: Simulated Database Crash
```

---

## Actual Output

```python
>>> import sys, io
>>> import unittest.mock as mock
>>> from ingest_api import app
>>> client = app.test_client()
>>> mock_conn = mock.MagicMock()
>>> mock_cur = mock.MagicMock()
>>> mock_conn.cursor.return_value.__enter__.return_value = mock_cur
>>> mock_cur.fetchone.side_effect = [[100], [500]]
>>> mock_close_run = mock.MagicMock()
>>> payload = {"hostname": "CRASH-TEST", "features": [{"user": "user"}]}
>>> 
>>> stderr_backup = sys.stderr
>>> sys.stderr = io.StringIO()
>>> 
>>> with mock.patch('ingest_api._connect', return_value=mock_conn):
...     with mock.patch('ingest_api._insert_features', side_effect=Exception("Simulated Database Crash")):
...         with mock.patch('ingest_api._close_run', mock_close_run):
...             response = client.post('/ingest', json=payload)
...             sys.stderr = stderr_backup
...             print(f"HTTP Status: {response.status_code}")
...             print(f"Error caught by API: {response.get_json()['error']}")
...             args, kwargs = mock_close_run.call_args
...             print(f"Run ID closed: {args[1]}")
...             print(f"Status saved to DB: {args[2]}")
...             print(f"Error saved to DB: {kwargs.get('error', '')}")
... 
HTTP Status: 500
Error caught by API: Simulated Database Crash
Run ID closed: 500
Status saved to DB: failed
Error saved to DB: Simulated Database Crash
```
