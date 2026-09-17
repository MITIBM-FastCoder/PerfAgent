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

import pandas as pd
import numpy as np
import pandas._testing as tm

N = 10**6
dtypes = [
    "Float64",
    "Int64",
    "int64[pyarrow]",
    "string",
    "string[pyarrow]",
]
method = None

# Prepare list of (Series, fill_value, dtype)
data_series = []

for dtype in dtypes:
    if dtype == "datetime64[ns]":
        data = pd.date_range("2000-01-01", freq="S", periods=N)
        na_value = pd.NaT
    elif dtype in ("float64", "Float64"):
        data = np.random.randn(N)
        na_value = np.nan
    elif dtype in ("Int64", "int64[pyarrow]"):
        data = np.arange(N)
        na_value = pd.NA
    elif dtype in ("string", "string[pyarrow]"):
        data = tm.rands_array(5, N)
        na_value = pd.NA

    fill_value = data[0]
    ser = pd.Series(data, dtype=dtype)
    ser[::2] = na_value
    data_series.append((ser, fill_value))

def workload():
    for ser, fill_value in data_series:
        ser.fillna(value=fill_value, method=None)
    
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
