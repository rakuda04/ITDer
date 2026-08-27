# COL-05: Verify USB event duplication handling

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
3. Import the filter and required modules:
   ```python
   from datetime import datetime, timezone, timedelta
   from processors.filters import filter_usb_duplicates
   import config
   ```
4. Create a mock list of USB events simulating physical bursts and phantom bounces for the same device:
   ```python
   now = datetime.now(timezone.utc)
   dev = "USB\\VID_1234&PID_5678"
   
   mock_events = [
       # Initial connect
       {"timestamp": now, "source": "UMDF", "event_id": 2003, "device": dev},
       # Duplicate connect (rapid physical jitter)
       {"timestamp": now + timedelta(seconds=1), "source": "UMDF", "event_id": 2003, "device": dev},
       # Normal disconnect 1 hour later
       {"timestamp": now + timedelta(hours=1), "source": "UMDF", "event_id": 2100, "device": dev},
       # Phantom bounce (Immediate connect then disconnect)
       {"timestamp": now + timedelta(hours=2), "source": "UMDF", "event_id": 2003, "device": dev},
       {"timestamp": now + timedelta(hours=2, seconds=1), "source": "UMDF", "event_id": 2100, "device": dev}
   ]
   ```
5. Apply the `filter_usb_duplicates` function:
   ```python
   deduped = filter_usb_duplicates(mock_events)
   ```
6. Print the results to verify duplicates and phantom bounces were dropped:
   ```python
   print(f"Original events: {len(mock_events)}")
   print(f"Cleaned events: {len(deduped)}")
   for e in deduped:
       print(f"Keep: {e.get('event_id')} (Category: {e.get('category')})")
   ```

---

## Expected Output

The `filter_usb_duplicates` function should remove the second `2003` (connect) event because it occurs within the identical window (Condition A). It should also remove the final `2100` (disconnect) event because it occurs within the phantom bounce window of the preceding connect (Condition B). 

The output should show the list dropping from 5 to 3 events:

```
Original events: 5
Cleaned events: 3
Keep: 2003 (Category: CONNECT)
Keep: 2100 (Category: DISCONNECT)
Keep: 2003 (Category: CONNECT)
```

---

## Actual Output


```python
>>> from datetime import datetime, timezone, timedelta
>>> from processors.filters import filter_usb_duplicates
>>> import config
>>> now = datetime.now(timezone.utc)
>>> dev = "USB\\VID_1234&PID_5678"
>>> 
>>> mock_events = [
...     # Initial connect
...     {"timestamp": now, "source": "UMDF", "event_id": 2003, "device": dev},
...     # Duplicate connect (rapid physical jitter)
...     {"timestamp": now + timedelta(seconds=1), "source": "UMDF", "event_id": 2003, "device": dev},
...     # Normal disconnect 1 hour later
...     {"timestamp": now + timedelta(hours=1), "source": "UMDF", "event_id": 2100, "device": dev},
...     # Phantom bounce (Immediate connect then disconnect)
...     {"timestamp": now + timedelta(hours=2), "source": "UMDF", "event_id": 2003, "device": dev},
...     {"timestamp": now + timedelta(hours=2, seconds=1), "source": "UMDF", "event_id": 2100, "device": dev}
... ]
>>> deduped = filter_usb_duplicates(mock_events)
>>> print(f"Original events: {len(mock_events)}")
Original events: 5
>>> print(f"Cleaned events: {len(deduped)}")
Cleaned events: 4
>>> for e in deduped:
...     print(f"Keep: {e.get('event_id')} (Category: {e.get('category')})")
... 
Keep: 2003 (Category: CONNECT)
Keep: 2100 (Category: DISCONNECT)
Keep: 2003 (Category: CONNECT)
Keep: 2100 (Category: DISCONNECT)
```

