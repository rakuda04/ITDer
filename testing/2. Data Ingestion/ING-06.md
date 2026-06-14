# ING-06: Verify payload-to-database insertion (`daily_features`)

**Test Type:** Integration  
**Status:** PASS  


---

## Prerequisites

- API server running (`docker compose up -d`)
- PostgreSQL database accessible (e.g., via `pgAdmin` or `psql`)

---

## Steps to Reproduce

1. Open **Postman** and create a new request:
   - **Method:** `POST`
   - **URL:** `http://localhost:8000/ingest`
2. Go to the **Body** tab, select **raw**, and choose **JSON** from the dropdown.
3. Paste the following payload and click **Send**:
   ```json
   {
     "hostname": "INGEST-TEST-PC",
     "features": [
       {
         "user": "test_analyst",
         "date": "2023-10-10",
         "total_active_minutes_day": 120.5,
         "usb_count": 3
       }
     ]
   }
   ```
4. Note the `run_id` returned in the successful HTTP response in Postman.
3. Open `pgAdmin` (or connect to Postgres via `psql`) and execute the following query against the `itder` database:
   ```sql
   SELECT d.hostname, f.username, f.feature_date, f.total_active_minutes_day, f.usb_count
   FROM daily_features f
   JOIN devices d ON f.device_id = d.device_id
   WHERE d.hostname = 'INGEST-TEST-PC';
   ```

---

## Expected Output

The database query must successfully return exactly 1 row, proving the JSON packet successfully traversed the API boundary, correctly parsed types, and committed cleanly to disk.

**Query Results:**
| hostname       | username     | feature_date | total_active_minutes_day | usb_count |
|----------------|--------------|--------------|--------------------------|-----------|
| INGEST-TEST-PC | test_analyst | 2023-10-10   | 120.5                    | 3         |


## Actual Output


```
{"rows_inserted":1,"run_id":35,"status":"ok"}
```



![alt text](../images/2.%20Data%20Ingestion/ing-03.png)
