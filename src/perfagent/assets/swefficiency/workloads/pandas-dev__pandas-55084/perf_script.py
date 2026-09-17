import timeit

timeit.template = """
def inner(_it, _timer{init}):
    {setup}
    _profile_duration = 10.0

    _t0 = _timer()
    for _i in _it:
        retval = {stmt}
    _t1 = _timer()

    _first_time = _t1 - _t0

    if _first_time >= _profile_duration:
        return _first_time

    _pad_start = _timer()
    while _timer() - _pad_start < _profile_duration:
        retval = {stmt}

    return _first_time
"""


import statistics

import numpy as np
import pandas as pd
import pandas._testing as tm

N = 10_000
dtypes = [
    "datetime64[ns]",
    "int64",
    "Int64",
    "int64[pyarrow]",
    "string[python]",
    "string[pyarrow]",
]
structures = ["monotonic", "non_monotonic", "has_na"]
axes = [0, 1]
sorts = [True, False]

series_registry = []


for dtype in dtypes:
    for structure in structures:
        for axis in axes:
            for sort in sorts:
                if dtype == "datetime64[ns]":
                    vals = pd.date_range("1970-01-01", periods=N)
                elif dtype in ("int64", "Int64", "int64[pyarrow]"):
                    vals = np.arange(N, dtype=np.int64)
                elif dtype in ("string[python]", "string[pyarrow]"):
                    vals = tm.makeStringIndex(N)
                else:
                    continue

                idx = pd.Index(vals, dtype=dtype)

                if structure == "monotonic":
                    idx = idx.sort_values()
                elif structure == "non_monotonic":
                    idx = idx[::-1]
                elif structure == "has_na":
                    if not idx._can_hold_na:
                        continue
                    idx = pd.Index([None], dtype=dtype).append(idx)
                else:
                    continue

                # Build a list of Series
                series_list = [pd.Series(i, idx[:-i]) for i in range(1, 6)]
                series_registry.append((series_list, axis, sort))

        
def workload():
    for series_list, axis, sort in series_registry:
        pd.concat(series_list, axis=axis, sort=sort)
            
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
