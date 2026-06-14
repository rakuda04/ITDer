# COL-09: Validate chronological sorting of final dataset

**Test Type:** Unit  
**Status:** PASS  

---

## Prerequisites

- Python 3.10+ installed
- `pandas` installed 
- Run from the `dist/local` directory

---

## Steps to Reproduce

1. Open a PowerShell or Terminal window and navigate to the `dist/local` directory.
2. Open a Python shell:
   ```
   python
   ```
3. Import pandas:
   ```python
   import pandas as pd
   ```
4. Create a mock dataset representing the merged data *before* the final sorting step. We deliberately scramble the dates and users:
   ```python
   mock_merged_df = pd.DataFrame([
       {"user": "user_b", "day": "10/12/2023", "usb_count": 1},
       {"user": "user_a", "day": "10/15/2023", "usb_count": 0},
       {"user": "user_b", "day": "10/10/2023", "usb_count": 2},
       {"user": "user_a", "day": "10/11/2023", "usb_count": 5}
   ])
   ```
5. Apply the exact sorting logic used by `local_preprocessor.py` (Lines 329-330) before the data is written out:
   ```python
   mock_merged_df['date'] = pd.to_datetime(mock_merged_df['day'], format='%m/%d/%Y')
   final_df = mock_merged_df.sort_values(by=['user', 'date']).reset_index(drop=True)
   ```
6. Print the result to verify it is grouped by user alphabetically, and then sorted chronologically within each user block:
   ```python
   for index, row in final_df.iterrows():
       print(f"User: {row['user']} | Date: {row['day']} | USB Count: {row['usb_count']}")
   
   # Programmatic verification
   is_sorted = (final_df['user'].is_monotonic_increasing and 
                final_df.groupby('user')['date'].apply(lambda x: x.is_monotonic_increasing).all())
   print(f"\nIs dataset correctly sorted by user and date? {is_sorted}")
   ```

---

## Expected Output

The data must first group `user_a` before `user_b`, and within each user, the dates must flow forwards in time (10/11 before 10/15, and 10/10 before 10/12). 

```
User: user_a | Date: 10/11/2023 | USB Count: 5
User: user_a | Date: 10/15/2023 | USB Count: 0
User: user_b | Date: 10/10/2023 | USB Count: 2
User: user_b | Date: 10/12/2023 | USB Count: 1

Is dataset correctly sorted by user and date? True
```


---

## Actual Output


```python
>>> import pandas as pd
>>> mock_merged_df = pd.DataFrame([
...     {"user": "user_b", "day": "10/12/2023", "usb_count": 1},
...     {"user": "user_a", "day": "10/15/2023", "usb_count": 0},
...     {"user": "user_b", "day": "10/10/2023", "usb_count": 2},
...     {"user": "user_a", "day": "10/11/2023", "usb_count": 5}
... ])
>>> mock_merged_df['date'] = pd.to_datetime(mock_merged_df['day'], format='%m/%d/%Y')
>>> final_df = mock_merged_df.sort_values(by=['user', 'date']).reset_index(drop=True)
>>> for index, row in final_df.iterrows():
...     print(f"User: {row['user']} | Date: {row['day']} | USB Count: {row['usb_count']}")
... 
User: user_a | Date: 10/11/2023 | USB Count: 5
User: user_a | Date: 10/15/2023 | USB Count: 0
User: user_b | Date: 10/10/2023 | USB Count: 2
User: user_b | Date: 10/12/2023 | USB Count: 1
>>> # Programmatic verification
>>> is_sorted = (final_df['user'].is_monotonic_increasing and 
...              final_df.groupby('user')['date'].apply(lambda x: x.is_monotonic_increasing).all())
>>> print(f"\nIs dataset correctly sorted by user and date? {is_sorted}")

Is dataset correctly sorted by user and date? True
```
