# COL-08: Graceful handling of missing/empty data sources

**Test Type:** Unit  
**Status:** PASS  
**Reference:** `testing/phase_1/COL-08.md`

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
3. Import the collection and processing orchestrator functions:
   ```python
   from data_collector import _process, _export
   import tempfile
   ```
4. Simulate a completely empty set of raw events (e.g., if a user just bought a new laptop or the time window is extremely narrow):
   ```python
   empty_events = []
   ```
5. Pass the empty list through the filter sequence:
   ```python
   cleaned_events = _process(empty_events)
   print(f"Length of cleaned list: {len(cleaned_events)}")
   ```
6. Verify the exporter gracefully handles the empty state without raising an exception:
   ```python
   with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
       _export(cleaned_events, tmp.name)
   ```

---

## Expected Output

The `_process` pipeline should easily return an empty list `[]` without triggering an index error or `KeyError` in the deduplication filters.
The `_export` function should gracefully catch the empty state and print a safe exit message rather than attempting to write an invalid CSV block.

```
[pipeline] Filtering startup noise...
[pipeline] Filtering USB events...
[pipeline] Deduplicating USB bursts...
Length of cleaned list: 0
[pipeline] No events to export.
```



## Actual Output


```python
>>> from data_collector import _process, _export
>>> import tempfile
>>> empty_events = []
>>> cleaned_events = _process(empty_events)
[pipeline] Filtering startup noise...
[pipeline] Filtering USB events...
[pipeline] Deduplicating USB bursts...
>>> print(f"Length of cleaned list: {len(cleaned_events)}")
Length of cleaned list: 0
>>> with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
...     _export(cleaned_events, tmp.name)
... 
[pipeline] No events to export.
```

