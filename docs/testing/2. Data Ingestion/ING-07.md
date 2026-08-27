# ING-07: Verify database duplicate avoidance (`ON CONFLICT`)

**Test Type:** Integration  
**Status:** PASS  

---

## Prerequisites

- API server running (`docker compose up -d`)
- PostgreSQL database accessible

---

## Steps to Reproduce

1. Open **Postman** and create a new request:
   - **Method:** `POST`
   - **URL:** `http://localhost:8000/ingest`
2. Go to the **Body** tab, select **raw**, and choose **JSON**. Paste the following payload:
   ```json
   {
     "hostname": "DUP-TEST-PC",
     "features": [
       {"user": "dup_user", "date": "2023-10-11", "usb_count": 1}
     ]
   }
   ```
3. Click **Send** to ingest the data for the first time.
4. Without changing any text in the body, click **Send** a second time to submit the exact same payload again.
2. Open `pgAdmin` (or connect via `psql`) and count the resulting rows:
   ```sql
   SELECT username, COUNT(*) as row_count 
   FROM daily_features 
   WHERE username = 'dup_user'
   GROUP BY username;
   ```

---

## Expected Output

Because the database schema implements `UNIQUE (device_id, username, feature_date)` constraints combined with the API's `ON CONFLICT DO NOTHING` logic, the second ingestion attempt is safely discarded instead of duplicating the row.

**Query Results:**
| username  | row_count |
|-----------|-----------|
| dup_user  | 1         |



## Actual Output

**1. Database Duplicate Verification:**
![Database Duplicate Verification](../images/2.%20Data%20Ingestion/ing-04-1.png)