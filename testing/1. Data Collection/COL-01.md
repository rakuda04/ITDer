# COL-01: Validate Windows Event Log Extraction

**Test Type:** Unit  
**Status:** PASS  

---

## Prerequisites

- Python 3.10+ installed
- Windows OS with access to Event Viewer
- `pywin32` installed (`pip install pywin32`)
- Terminal or PowerShell run as **Administrator** (required to read Security and UMDF logs)

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/local` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import both collector functions:
   ```python
   from collectors.windows_events import get_umdf_events, get_security_events
   ```
4. Run the UMDF collector for the past 7 days:
   ```python
   umdf = get_umdf_events(days=7)
   print(f"UMDF events: {len(umdf)}")
   ```
5. Run the Security event collector for the past 7 days:
   ```python
   security = get_security_events(days=7)
   print(f"Security events: {len(security)}")
   ```
6. Inspect a sample entry to confirm structure:
   ```python
   print(umdf[0] if umdf else "No UMDF events found")
   print(security[0] if security else "No Security events found")
   ```

---

## Expected Output

Both calls return without throwing an exception. Each result is a list of dictionaries. A sample entry should contain at minimum the following keys:

**UMDF event:**
```
{
  'timestamp': datetime(..., tzinfo=...),
  'source': 'UMDF',
  'event_id': <int>,
  'device': '<device instance string>',
  'user': '<username>'
}
```

**Security event:**
```
{
  'timestamp': datetime(..., tzinfo=...),
  'source': 'Security',
  'event_id': <int>,
  'activity': 'LOGON(STARTUP)' | 'LOGOFF(shutdown)' | ...,
  'user': '<username>',
  'logon_id': '<str>'
}
```


---

## Actual Output



```python
>>> from collectors.windows_events import get_umdf_events, get_security_events
>>> 
>>> # Run the UMDF collector for the past 7 days:
>>> umdf = get_umdf_events(days=7)
>>> print(f"UMDF events: {len(umdf)}")
UMDF events: 413
>>> 
>>> # Run the Security event collector for the past 7 days:
>>> security = get_security_events(days=7)
>>> print(f"Security events: {len(security)}")
Security events: 324
>>> 
>>> # Inspect a sample entry to confirm structure:
>>> print(umdf[0] if umdf else "No UMDF events found")
{'timestamp': datetime.datetime(2026, 6, 8, 15, 39, 8, 566471, tzinfo=datetime.timezone(datetime.timedelta(seconds=10800), 'Arab Standard Time')), 'source': 'UMDF', 'event_id': 2100, 'device': 'SWD\\WPDBUSENUM\\_??_USBSTOR#DISK&VEN_SANDISK&PROD_CRUZER_BLADE&REV_1.00#1234567890&0#{53F56307-B6BF-11D0-94F2-00A0C91EFB8B}', 'user': 'user'}
>>> print(security[0] if security else "No Security events found")
{'timestamp': datetime.datetime(2026, 6, 6, 9, 54, 28, 468411, tzinfo=datetime.timezone(datetime.timedelta(seconds=10800), 'Arab Standard Time')), 'source': 'Security', 'event_id': 4800, 'activity': 'LOCK', 'user': 'user', 'logon_id': '0x1c1c4e'}
```


