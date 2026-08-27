# ING-01: Validate API rejection of malformed payloads

**Test Type:** Unit  
**Status:** PASS  

---

## Prerequisites

- Python 3.10+ installed
- `flask` and `psycopg2-binary` installed (`pip install flask psycopg2-binary`)
- Run from the `dist/server` directory

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/server` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import the Flask app and test client:
   ```python
   from ingest_api import app
   client = app.test_client()
   ```
4. Send an empty JSON payload to the `/ingest` endpoint:
   ```python
   response_empty = client.post('/ingest', json={})
   print(f"Empty Payload Status: {response_empty.status_code}")
   print(f"Empty Payload Response: {response_empty.get_json()}")
   ```
5. Send a payload missing all three data arrays (`features`, `scores`, `user_risk`):
   ```python
   response_no_data = client.post('/ingest', json={"hostname": "TEST-PC"})
   print(f"No Data Status: {response_no_data.status_code}")
   print(f"No Data Response: {response_no_data.get_json()}")
   ```

---

## Expected Output

The API must gracefully intercept both requests, returning HTTP 400 Bad Request instead of throwing a 500 server error or crashing the worker thread.

```
Empty Payload Status: 400
Empty Payload Response: {'error': 'no data provided'}
No Data Status: 400
No Data Response: {'error': 'no data provided'}
```



## Actual Output


```python
>>> from ingest_api import app
>>> client = app.test_client()
>>> response_empty = client.post('/ingest', json={})
>>> print(f"Empty Payload Status: {response_empty.status_code}")
Empty Payload Status: 400
>>> print(f"Empty Payload Response: {response_empty.get_json()}")
Empty Payload Response: {'error': 'expected JSON body'}
>>> response_no_data = client.post('/ingest', json={"hostname": "TEST-PC"})
>>> print(f"No Data Status: {response_no_data.status_code}")
No Data Status: 400
>>> print(f"No Data Response: {response_no_data.get_json()}")
No Data Response: {'error': 'no data provided'}
```
