### Chapter 6: Testing

**6.1 The Goal of The Test**

The primary goal of this testing phase is to validate the functionality, accuracy, and integration of the Insider Threat Detection System. Testing ensures that data is accurately collected from the local endpoints, safely transported and stored in the database, properly processed and scored by the machine learning models, and correctly visualized on the security dashboard.

**6.2 Testing Methodology**

The project utilized a Pipeline/Data-Flow Testing Methodology. Because the system functions as a distributed Extract, Transform, Load (ETL) and Machine Learning pipeline, testing was conducted chronologically. Rather than separating unit tests from integration tests, the testing framework follows the exact lifecycle of the data as it moves through the system. This methodology is divided into four main phases, incorporating Unit, Integration, and System/E2E testing at each relevant stage:

1. **Phase 1: Endpoint Data Collection:** Validating the extraction, filtering, and formatting of local Windows event logs.
    
2. **Phase 2: Data Ingestion & Storage:** Ensuring the backend Flask API accurately receives, validates, and stores the payload in the PostgreSQL database.
    
3. **Phase 3: Machine Learning & Processing:** Testing the Inference Worker's ability to pull data, apply anomaly detection models (Isolation Forest, Elliptic Envelope), and calculate SHAP feature attributions.
    
4. **Phase 4: Dashboard & Alerting:** Verifying the React UI correctly renders the risk scores and simulating a full end-to-end insider threat scenario.
    

**6.3 Testing Environment**

To ensure consistency and reliability, all tests were conducted in a controlled environment. The hardware and software specifications used during the testing phase are detailed below:

- **Hardware:** Intel Core i7 Processor, 16GB RAM, 512GB SSD 
    
- **Operating System:** Windows 11 (Local Agent) and Ubuntu Linux via WSL (Backend/Server).
    
- **Software & Frameworks:** Python 3.10, Node.js, React, Docker, and PostgreSQL.
    
- **Testing Tools:** Postman for API endpoint testing, pgAdmin for database verification, and standard web browsers Chrome for UI testing.
    

**6.4 Phase 1: Endpoint Data Collection** This phase tests the local origin of the data. It ensures that the Windows endpoint scripts can accurately gather system logs, filter out noise, and prepare the data payload for transmission.

| **Test ID** | **Test Type** | **Test Description**                                     | **Expected Result**                                                                                           | **Actual Result**                                                      | **Status** | **Reference File**          |
| ----------- | ------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ---------- | --------------------------- |
| **COL-01**  | Unit          | Validate Windows Event log extraction.                   | Functions pull raw events from Windows Event Viewer without crashing.                                         | Raw USB and Security logs successfully extracted into memory.          | PASS       | `testing/1. Data Collection/COL-01.md` |
| **COL-02**  | Unit          | Validate Browser History extraction.                     | Returns a structured list of visited URLs and timestamps.                                                     | Array of browser history dictionaries successfully populated.          | PASS       | `testing/1. Data Collection/COL-02.md` |
| **COL-03**  | Unit          | Verify date bounding parameter (`days`).                 | All returned events strictly fall within the requested time window.                                           | No out-of-bounds timestamps were found in the output.                  | PASS       | `testing/1. Data Collection/COL-03.md` |
| **COL-04**  | Unit          | Test startup noise and non-USB filters.                  | Boot-time logon noise is suppressed and non-USB events are removed.                                           | Cleaned dataset was generated, leaving only relevant USB bursts.       | PASS       | `testing/1. Data Collection/COL-04.md` |
| **COL-05**  | Unit          | Verify USB event duplication handling.                   | Consecutive rapid USB connection/disconnection events are collapsed.                                          | Redundant USB bursts merged into a single logical session.             | PASS       | `testing/1. Data Collection/COL-05.md` |
| **COL-06**  | Unit          | Validate session pairing logic (Logon/Logoff).           | Events are correctly paired to compute session durations, with unclosed sessions capped at midnight.          | Total active minutes computed correctly with midnight boundary bounds. | PASS       | `testing/1. Data Collection/COL-06.md` |
| **COL-07**  | Unit          | Test 7-day rolling compound feature generation.          | Flag is correctly set when a job search and a USB insertion occur within the same 7-day rolling window.       | `job_search_plus_usb_week` accurately generated based on thresholds.   | PASS       | `testing/1. Data Collection/COL-07.md` |
| **COL-08**  | Unit          | Graceful handling of missing/empty data sources.         | If no logs exist over the query window, the pipeline executes without crashing and exports a blank schema.    | Handled empty source lists securely without throwing exceptions.       | PASS       | `testing/1. Data Collection/COL-08.md` |
| **COL-09**  | Unit          | Validate chronological sorting of final dataset.         | The finalized data frame is sorted securely by user and sequential date before output mapping.                | Output file correctly indexed by date across all users.                | PASS       | `testing/1. Data Collection/COL-09.md` |
| **COL-10**  | Unit          | Validate output CSV generation.                          | `activity_report.csv` is created correctly with all necessary field names and formatted timestamps.           | CSV successfully written with correct headers and UTC strings.         | PASS       | `testing/1. Data Collection/COL-10.md` |
| **COL-11**  | Unit          | Validate final CERT schema compliance.                   | The output `local_model_intake.csv` strictly contains all 16 predefined columns in the correct order.         | Final preprocessed CSV perfectly aligns with the target schema.        | PASS       | `testing/1. Data Collection/COL-11.md` |
| **COL-12**  | Integration   | Test carryover days without a STARTUP event.             | Days where the machine was never turned off correctly assign `NaN` to `total_active_minutes_day`.             | Carry-over days properly handled without false zero values.            | PASS       | `testing/1. Data Collection/COL-12.md` |
| **COL-13**  | Integration   | Verify data orchestrator pipeline (`data_collector.py`). | All data sources are collected, filtered, and merged into a single chronologically sorted list.               | Pipeline successfully combined and sorted all event types.             | PASS       | `testing/1. Data Collection/COL-13.md` |
| **COL-14**  | Integration   | Validate Z-score baseline requirements.                  | Z-scores are correctly calculated only when a user's logon history meets the `min_baseline_days` requirement. | Returns `NaN` and correctly sets flag to `0` when under minimum days.  | PASS       | `testing/1. Data Collection/COL-14.md` |
| **COL-15**  | Integration   | Verify after-hours and weekend flag assignment.          | USB/Logon events outside business hours or on weekends correctly trigger their respective flags.              | After-hours and weekend variables successfully populated.              | PASS       | `testing/1. Data Collection/COL-15.md` |

**6.5 Phase 2: Data Ingestion and Storage** This phase follows the data as it leaves the endpoint and arrives at the backend server. It tests the Flask API's ability to validate incoming data and the successful integration with the PostgreSQL database.

|**Test ID**|**Test Type**|**Test Description**|**Expected Result**|**Actual Result**|**Status**|**Reference File**|
|---|---|---|---|---|---|---|
|**ING-01**|Unit|Validate API rejection of malformed payloads.|API rejects the payload, returning HTTP 400 `{"error": "no data provided"}` or `expected JSON body`.|Server safely rejected malformed data without crashing.|PASS|`testing/2. Data Ingestion/ING-01.md`|
|**ING-02**|Unit|Validate API device registration and ingestion.|API registers the new machine, returning an HTTP 200 OK status.|Returned HTTP 200 OK with dynamically generated `run_id`.|PASS|`testing/2. Data Ingestion/ING-02.md`|
|**ING-03**|Unit|Validate API data typing safety (`_safe_int`, `_safe_float`).|Nulls or garbage strings safely fallback to `None` without crashing the database insertion loops.|Bad input strings were gracefully sanitized to Null types.|PASS|`testing/2. Data Ingestion/ING-03.md`|
|**ING-04**|Unit|Test endpoint connection loss during transmit.|If the API server is down, `send_to_server.py` catches the connection error and cleanly exits instead of unhandled stack.|Script correctly caught `requests.exceptions.ConnectionError`.|PASS|`testing/2. Data Ingestion/ING-04.md`|
|**ING-05**|Unit|Validate transaction error handling (`pipeline_runs`).|If a database insertion exception occurs mid-payload, the run status updates to "failed" and saves the error message.|Error successfully caught and `pipeline_runs` status updated to failed.|PASS|`testing/2. Data Ingestion/ING-05.md`|
|**ING-06**|Integration|Verify payload-to-database insertion (`daily_features`).|API successfully inserts a new row into the `daily_features` table.|Queried pgAdmin; feature rows matched the JSON payload exactly.|PASS|`testing/2. Data Ingestion/ING-06.md`|
|**ING-07**|Integration|Verify database duplicate avoidance (`ON CONFLICT`).|Re-sending the exact same data payload for the same day does not duplicate rows in Postgres.|`ON CONFLICT DO NOTHING` successfully ignored the duplicate database insertions.|PASS|`testing/2. Data Ingestion/ING-07.md`|

**6.6 Phase 3: Machine Learning and Processing** Once the data is securely stored in the PostgreSQL database, it enters the processing phase. These tests validate the background inference worker, ensuring that the machine learning models accurately score the data and that the synthetic generator creates valid baselines.

| Test ID   | Test Type   | Test Description                                       | Expected Result                                                       | Actual Result                                                         | Status | Reference File             |
| --------- | ----------- | ------------------------------------------------------ | --------------------------------------------------------------------- | --------------------------------------------------------------------- | ------ | -------------------------- |
| **ML-01** | Unit        | Create a baseline population matching CERT parameters. | Outputs CSV containing configured counts of normal and insider users. | CSV generated with highly realistic randomized feature distributions. | PASS   | `testing/3. Machine Learning/ML-01.md` |
| **ML-02** | Unit        | Pass a controlled malicious vector to the models.      | IsoForest and Elliptic Envelope return an anomaly prediction of `-1`. | Scored malicious vector successfully; `flagged_by_both` set to 1.     | PASS   | `testing/3. Machine Learning/ML-02.md` |
| **ML-03** | Unit        | Verify SHAP value calculations for a flagged row.      | Algorithm generates attribution scores identifying driving variables. | Output a DataFrame of SHAP values matching feature dimensions.        | PASS   | `testing/3. Machine Learning/ML-03.md` |
| **ML-04** | Integration | Trigger `inference_worker.py` to execute a full run.   | Worker applies models and writes results to `daily_scores` table.     | Worker completed run seamlessly; Postgres tables populated.           | PASS   | `testing/3. Machine Learning/ML-04.md` |

**6.7 Phase 4: Dashboard and End-to-End** This final phase represents the destination of the data flow: the security analyst's screen. These tests validate that the React dashboard correctly interprets the database scores, renders visual cues, and successfully acts as a single pane of glass for the entire pipeline.
# Phase 4: Dashboard and  End-to-End

|**Test ID**|**Test Type**|**Test Description**|**Expected Result**|**Actual Result**|**Status**|**Reference File**|
|---|---|---|---|---|---|---|
|**UI-01**|Unit|Verify data APIs return correctly typed JSON.|`/api/users`, `/api/daily`, and `/api/shap` each return a typed JSON array with numeric fields correctly coerced from CSV strings.|All three endpoints returned well-formed arrays with correct int and float types.|PASS|`testing/4. Dashboard/UI-01.md`|
|**UI-02**|Integration|Validate Settings panel passes synthetic config to subprocess.|Submitting a custom synthetic config via the Settings panel correctly passes all parameters as env vars to `synthetic_generator.py`.|Subprocess received correct env vars; generation completed with expected user counts.|PASS|`testing/4. Dashboard/UI-02.md`|
|**UI-03**|Integration|Validate Settings panel triggers inference subprocess.|Clicking "Run inference" in the Settings panel invokes `inference.py` as a subprocess and returns `{"ok": true}` to the dashboard.|Inference subprocess executed successfully; dashboard received confirmation response.|PASS|`testing/4. Dashboard/UI-03.md`|
|**UI-04**|Integration|Verify user selection correctly filters timeline and SHAP data.|Switching the selected user in the dropdown filters both `dailyAll` and `shapAll` arrays to only return rows matching that user.|Timeline chart and SHAP tab updated correctly to reflect only the selected user's records.|PASS|`testing/4. Dashboard/UI-04.md`|
|**E2E-01**|System|Validate full pipeline data flow from endpoint to dashboard.|Raw events collected on the endpoint flow through preprocessing, ingestion, and inference; the dashboard leaderboard reflects the scored output with correct risk tiers.|Data traversed all pipeline stages; dashboard displayed accurate risk rankings and scores.|PASS|`testing/4. Dashboard/E2E-01.md`|
|**E2E-02**|System|Verify dashboard-triggered run updates displayed results.|Running synthetic generation then inference from the Settings panel causes the dashboard to reload and display freshly scored leaderboard data.|Both subprocesses completed via the dashboard; reloaded UI showed updated scores and ranks.|PASS|`testing/4. Dashboard/E2E-02.md`|
# 6.8 Evaluation and Metrics of Machine Learning Models

To evaluate the effectiveness of the detection pipeline, all three machine learning models were assessed against the synthetic population generated by `synthetic_generator.py`. This population consists of **27 normal users** and **3 insider users** across **90 days**, where ground truth labels (`insider_label`) are known by construction. Because real-world data does not explicitly label which users are true threats, the synthetic population serves as the controlled evaluation environment, reflecting realistic behavioral distributions derived from the CERT Insider Threat Dataset r4.2.

Each model's predictions were compared against the known `insider_label` field to compute standard classification metrics.

---

## 6.8.1 Individual Model Performance

|**Model**|**Precision**|**Recall**|**F1-Score**|**AUC-ROC**|**False Positive Rate**|
|---|---|---|---|---|---|
|Random Forest (Supervised)|0.65|0.33|0.44|0.77|0.01|
|IsoForest (Unsupervised)|0.61|1.00|0.76|0.99|0.05|
|Elliptic Envelope (Unsupervised)|0.62|1.00|0.76|1.00|0.05|
|**Combined Ensemble**|**0.75**|**0.73**|**0.74**|**0.99**|**0.02**|
---

### 6.8.2 Understanding the Metrics Columns
- **Precision:** Percentage of alerts that are actual threats (minimizes false alarms).
- **Recall:** Percentage of actual threats that the model successfully caught.
- **F1-Score:** The mathematical balance between Precision and Recall.
- **AUC-ROC:** The model's ability to accurately rank threat days higher than normal days.
- **False Positive Rate:** Percentage of normal days incorrectly flagged as threats.


### 6.8.3 Model Summary
The supervised classification model is highly conservative focused on known threats patterns, while the unsupervised anomaly detectors capture everything acting as sensitive tripwires. The Combined Ensemble averages their signals to balance them out providing the precision of the supervised model while retaining the broad recall of the unsupervised ones.


