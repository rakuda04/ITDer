# COL-02: Validate Browser History Extraction

**Test Type:** Unit  
**Status:** PASS  
**Reference:** `testing/phase_1/COL-02.md`

---

## Prerequisites

- Python 3.10+ installed
- At least one supported browser installed and with browsing history (Chrome, Edge, Brave, Opera, Vivaldi, or Firefox)
- Run from the `dist/local`

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/local` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import the collector function:
   ```python
   from collectors.browser_history import get_browser_history
   ```
4. Run the collector for the past 7 days:
   ```python
   history = get_browser_history(days=7)
   print(f"Total browser entries: {len(history)}")
   ```
5. Inspect a sample entry to confirm structure:
   ```python
   print(history[0] if history else "No browser history found")
   ```
6. Verify all entries contain the expected keys:
   ```python
   print(all('url' in e and 'timestamp' in e and 'browser' in e for e in history))
   ```

---

## Expected Output

The collector scans all installed browsers automatically and prints which ones it found. Step 4 should print something like:

```
[browser_history] Found Chrome: C:\Users\...\Chrome\User Data\Default\History
  → 142 entries
Total browser entries: 142
```

entry from step 5 should match this structure:

```
{
  'timestamp': datetime(..., tzinfo=...),
  'source': 'Browser',
  'event_id': None,
  'browser': 'Chrome',
  'url': 'https://example.com',
  'title': 'Example Domain',
  'visit_count': 3,
  'user': '<username>'
}
```

Step 6 should print `True`, confirming all entries are well-formed. 


---

## Actual Output

```python
>>> from collectors.browser_history import get_browser_history
>>> history = get_browser_history(days=7)
[browser_history] Found Edge: C:\Users\user\AppData\Local\Microsoft\Edge\User Data\Default\History
  → 0 entries
[browser_history] Found Firefox: C:\Users\user\AppData\Roaming\Mozilla\Firefox\Profiles\profile.default-release\places.sqlite
  → 1915 entries
[browser_history] Found Firefox: C:\Users\user\AppData\Roaming\Mozilla\Firefox\Profiles\profile.default-release\places.sqlite
  → 1915 entries
>>> print(f"Total browser entries: {len(history)}")
Total browser entries: 3847
>>> print(history[0] if history else "No browser history found")
{'timestamp': datetime.datetime(2026, 6, 6, 8, 4, 27, 365000, tzinfo=datetime.timezone(datetime.timedelta(seconds=10800), 'Arab Standard Time')), 'source': 'Browser', 'event_id': None, 'browser': 'Firefox', 'url': 'https://github.com/explore', 'title': 'Explore GitHub', 'visit_count': 5, 'user': 'user'}
>>> print(all('url' in e and 'timestamp' in e and 'browser' in e for e in history))
True
```

