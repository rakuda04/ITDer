# COL-13: Verify data orchestrator pipeline (`data_collector.py`)

**Test Type:** Integration  
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
3. Import the orchestrator's `_collect` function:
   ```python
   from data_collector import _collect
   ```
4. Run the collector for a small window (e.g., 7 days):
   ```python
   combined_events = _collect(days=7)
   ```
5. Verify the list contains merged events from multiple distinct sources:
   ```python
   sources = set(e.get("source") for e in combined_events)
   print(f"Total merged events: {len(combined_events)}")
   print(f"Distinct sources collected: {sources}")
   ```
6. Verify the entire combined list is correctly sorted chronologically:
   ```python
   is_sorted = all(
       combined_events[i]["timestamp"] <= combined_events[i+1]["timestamp"] 
       for i in range(len(combined_events) - 1)
   )
   print(f"Is chronologically sorted? {is_sorted}")
   ```

---

## Expected Output

Step 5 should show that events were gathered from multiple collectors (e.g., UMDF, Browser, Security). Step 6 must output `True`, confirming that the orchestrated merge properly aligned disparate data streams onto a single chronological timeline.

```
Total merged events: [some integer > 0]
Distinct sources collected: {'UMDF', 'Browser', 'Security'}
Is chronologically sorted? True
```
---

## Actual Output


```python
>>> from data_collector import _collect
>>> combined_events = _collect(days=7)
[pipeline] Collecting Windows UMDF events...
[pipeline] Collecting Windows security events...
[pipeline] Collecting browser history...
[browser_history] Found Edge: C:\Users\user\AppData\Local\Microsoft\Edge\User Data\Default\History
  → 0 entries
[browser_history] Found Firefox: C:\Users\user\AppData\Roaming\Mozilla\Firefox\Profiles\profile.default-release\places.sqlite
  → 1701 entries
>>> sources = set(e.get("source") for e in combined_events)
>>> print(f"Total merged events: {len(combined_events)}")
Total merged events: 4132
>>> print(f"Distinct sources collected: {sources}")
Distinct sources collected: {'Browser', 'System', 'UMDF', 'Security'}
>>> is_sorted = all(
...     combined_events[i]["timestamp"] <= combined_events[i+1]["timestamp"] 
...     for i in range(len(combined_events) - 1)
... )
>>> print(f"Is chronologically sorted? {is_sorted}")
Is chronologically sorted? True
```


