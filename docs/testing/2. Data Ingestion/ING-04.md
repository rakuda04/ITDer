# ING-04: Test endpoint connection loss during transmit

**Test Type:** Unit 
**Status:** PASS  

---

## Prerequisites

- Python 3.10+ installed
- Run from the `dist/local` directory (this tests the client-side sender)
- You must have `local_model_intake.csv` generated in `dist/local/output/` .Run `python local_preprocessor.py` if missing.

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/local` directory.
2. Temporarily set the `ITDER_API_URL` environment variable to a server address that does not exist to simulate a network outage:
   

   ```powershell
   $env:ITDER_API_URL="http://localhost:9999"
   ```

3. Execute the server-upload script:
   ```bash
   python send_to_server.py
   ```
4. Observe the terminal output and check the exit code:

   ```powershell
   echo $LASTEXITCODE
   ```
 

---

## Expected Output

The script successfully catches the `requests.exceptions.ConnectionError` thrown when it fails to route to `localhost:9999`. Instead of dumping a massive, unhandled Python stack trace onto the endpoint user's screen, it prints a clean error message and exits cleanly with a status code of `1`.

```
[server] Loading CSVs...
[server] Posting to http://localhost:9999/ingest...
[server] Could not reach server. Check ITDER_API_URL and internet connection.
1
```




## Actual Output


```powershell
PS C:\Users\user\dist\local> $env:ITDER_API_URL="http://localhost:9999"
PS C:\Users\user\dist\local> python send_to_server.py
[server] Loading CSVs...
[server] Posting to http://localhost:9999/ingest...
[server] Could not reach server. Check ITDER_API_URL and internet connection.
PS C:\Users\user\dist\local> echo $LASTEXITCODE
1
```
