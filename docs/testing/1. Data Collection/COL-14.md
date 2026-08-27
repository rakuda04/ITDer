# COL-14: Validate Z-score baseline requirements

**Test Type:** Integration  
**Status:** PASS  
**Reference:** `testing/phase_1/COL-14.md`

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
3. Import the required modules and the Z-score calculation function:
   ```python
   import numpy as np
   import pandas as pd
   from local_preprocessor import _calculate_zscore
   ```
4. Create a mock DataFrame testing two scenarios: a user without a baseline (3 days) and a user with a baseline (5 days):
   ```python
   mock_daily = pd.DataFrame([
       # Scenario 1: User without baseline (3 days)
       {"user": "user_no_baseline", "usb_count": 2},
       {"user": "user_no_baseline", "usb_count": 4},
       {"user": "user_no_baseline", "usb_count": 1},
       
       # Scenario 2: User with baseline (5 days)
       {"user": "user_has_baseline", "usb_count": 2},
       {"user": "user_has_baseline", "usb_count": 4},
       {"user": "user_has_baseline", "usb_count": 1},
       {"user": "user_has_baseline", "usb_count": 5},
       {"user": "user_has_baseline", "usb_count": 3}
   ])
   ```
5. Run the Z-score logic with `min_baseline_days = 5`:
   ```python
   result = _calculate_zscore(
       df=mock_daily,
       user_col='user',
       value_col='usb_count',
       new_col_name='usb_count_zscore',
       min_baseline_days=5
   )
   ```
6. Verify the computed Z-scores and flags for both users:
   ```python
   no_baseline_row = result[result['user'] == 'user_no_baseline'].iloc[0]
   print(f"User without baseline - Z-score: {no_baseline_row['usb_count_zscore']}")
   print(f"User without baseline - Flag: {no_baseline_row['usb_count_zscore_has_baseline']}")

   has_baseline_row = result[result['user'] == 'user_has_baseline'].iloc[0]
   print(f"User with baseline - Z-score: {has_baseline_row['usb_count_zscore']:.2f}")
   print(f"User with baseline - Flag: {has_baseline_row['usb_count_zscore_has_baseline']}")
   ```

---

## Expected Output

Because `user_no_baseline` only has 3 days of history and the minimum is 5, the pipeline refuses to calculate a statistically insignificant Z-score. It assigns `NaN` to the score and correctly sets the `has_baseline` flag to `0`. However, `user_has_baseline` has 5 days of history, so their Z-score is calculated normally and their flag is set to `1`.

```
User without baseline - Z-score: nan
User without baseline - Flag: 0
User with baseline - Z-score: -0.63
User with baseline - Flag: 1
```

**📸 Screenshot:** Take a screenshot of the terminal showing the output of step 6, proving that baseline constraints are successfully enforced.

---

## Actual Output


```python
>>> import numpy as np
>>> import pandas as pd
>>> from local_preprocessor import _calculate_zscore
>>> mock_daily = pd.DataFrame([
...     # Scenario 1: User without baseline (3 days)
...     {"user": "user_no_baseline", "usb_count": 2},
...     {"user": "user_no_baseline", "usb_count": 4},
...     {"user": "user_no_baseline", "usb_count": 1},
...     
...     # Scenario 2: User with baseline (5 days)
...     {"user": "user_has_baseline", "usb_count": 2},
...     {"user": "user_has_baseline", "usb_count": 4},
...     {"user": "user_has_baseline", "usb_count": 1},
...     {"user": "user_has_baseline", "usb_count": 5},
...     {"user": "user_has_baseline", "usb_count": 3}
... ])
>>> result = _calculate_zscore(
...     df=mock_daily,
...     user_col='user',
...     value_col='usb_count',
...     new_col_name='usb_count_zscore',
...     min_baseline_days=5
... )
>>> no_baseline_row = result[result['user'] == 'user_no_baseline'].iloc[0]
>>> print(f"User without baseline - Z-score: {no_baseline_row['usb_count_zscore']}")
User without baseline - Z-score: nan
>>> print(f"User without baseline - Flag: {no_baseline_row['usb_count_zscore_has_baseline']}")
User without baseline - Flag: 0
>>> has_baseline_row = result[result['user'] == 'user_has_baseline'].iloc[0]
>>> print(f"User with baseline - Z-score: {has_baseline_row['usb_count_zscore']:.2f}")
User with baseline - Z-score: -0.63
>>> print(f"User with baseline - Flag: {has_baseline_row['usb_count_zscore_has_baseline']}")
User with baseline - Flag: 1
```


