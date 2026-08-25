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

n_rows, n_cols = 1_000_000, 10

# construct dataframe with 2 blocks
arr1 = np.random.randn(n_rows, n_cols // 2).astype("f8")
arr2 = np.random.randn(n_rows, n_cols // 2).astype("f4")
df = pd.concat([pd.DataFrame(arr1), pd.DataFrame(arr2)], axis=1, ignore_index=True)
df._consolidate_inplace()

arr1 = np.random.randn(n_rows, max(n_cols // 4, 3)).astype("f8")
arr2 = np.random.randn(n_rows, n_cols // 2).astype("i8")
arr3 = np.random.randn(n_rows, n_cols // 4).astype("f8")
df2 = pd.concat(
    [pd.DataFrame(arr1), pd.DataFrame(arr2), pd.DataFrame(arr3)],
    axis=1,
    ignore_index=True,
)
df2._consolidate_inplace()

def workload():
    df > df2
    
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
