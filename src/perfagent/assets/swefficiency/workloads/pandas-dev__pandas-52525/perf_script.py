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

N = 10_000_000
data = np.random.randn(N)
arr1 = pd.array(data, dtype="float64[pyarrow]")
arr2 = pd.array(data, dtype="float64[pyarrow]")
arr2[::1000] = None
arr3 = pd.array([None] * N, dtype="null[pyarrow]")

def workload():
    arr1.to_numpy("float64")
    arr2.to_numpy("float64", na_value=np.nan)
    arr3.to_numpy("float64", na_value=np.nan)

# Measure runtime
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
