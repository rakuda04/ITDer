# COL-04: Test startup noise and non-USB filters

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
3. Import the filters and required modules:
   ```python
   from collectors.windows_events import get_umdf_events, get_security_events
   from processors.filters import filter_usb_only, filter_startup_noise
   
   # 1. Fetch real events from the last 7 days
   umdf_raw = get_umdf_events(days=7)
   sec_raw = get_security_events(days=7)
   
   # Combine and sort chronologically
   raw_events = umdf_raw + sec_raw
   raw_events.sort(key=lambda x: x["timestamp"])
   
   print(f"Total raw events fetched: {len(raw_events)}")
   
   # 2. Apply USB filter
   usb_only = filter_usb_only(raw_events)
   dropped_non_usb = len(raw_events) - len(usb_only)
   print(f"Events after USB filter: {len(usb_only)} (Dropped {dropped_non_usb} non-USB devices)")
   
   # 3. Apply Startup noise filter
   startup_cleaned = filter_startup_noise(usb_only)
   dropped_startup = len(usb_only) - len(startup_cleaned)
   print(f"Events after startup noise filter: {len(startup_cleaned)} (Dropped {dropped_startup} boot-time system logons)")
   ```

---

## Expected Output

The script should fetch your actual Windows event logs and mathematically show the noise-reduction filters at work. 
You should see the "USB filter" drop a large amount of events (like internal hard drives, PCI bridges, or network adapters) and the "startup noise filter" drop the rapid burst of `LOGON` events that Windows fires internally when it first boots up.

**example output**
```
Total raw events fetched: 350
Events after USB filter: 150 (Dropped 200 non-USB devices)
Events after startup noise filter: 145 (Dropped 5 boot-time system logons)
```



## Actual Output

```python
>>> from collectors.windows_events import get_umdf_events, get_security_events
>>> from processors.filters import filter_usb_only, filter_startup_noise
>>> 
>>> # 1. Fetch real events from the last 7 days
>>> umdf_raw = get_umdf_events(days=7)
>>> sec_raw = get_security_events(days=7)
>>> 
>>> # Combine and sort chronologically
>>> raw_events = umdf_raw + sec_raw
>>> raw_events.sort(key=lambda x: x["timestamp"])
>>> 
>>> print(f"Total raw events fetched: {len(raw_events)}")
Total raw events fetched: 716
>>> 
>>> # 2. Apply USB filter
>>> usb_only = filter_usb_only(raw_events)
>>> dropped_non_usb = len(raw_events) - len(usb_only)
>>> print(f"Events after USB filter: {len(usb_only)} (Dropped {dropped_non_usb} non-USB devices)")
Events after USB filter: 516 (Dropped 200 non-USB devices)
>>> 
>>> # 3. Apply Startup noise filter
>>> startup_cleaned = filter_startup_noise(usb_only)
>>> dropped_startup = len(usb_only) - len(startup_cleaned)
>>> print(f"Events after startup noise filter: {len(startup_cleaned)} (Dropped {dropped_startup} boot-time system logons)")
Events after startup noise filter: 317 (Dropped 199 boot-time system logons)
```

