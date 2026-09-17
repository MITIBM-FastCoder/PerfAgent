
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

N = 10 ** 5
N_groupby = 100

arr_options = [
    (100 * np.random.random(N)).astype(dtype)
    for dtype in ["int", "float"]
]
expanding_groupby_options = [
    pd.DataFrame({"A": arr[:N_groupby], "B": range(N_groupby)}).groupby("B").expanding()
    for arr in arr_options
]
methods = ["median", "mean", "max", "min", "std", "count", "sum"]

def workload():
    for expanding_groupby in expanding_groupby_options:
        for method in methods:
            # Using timeit to measure the execution time of each method
            getattr(expanding_groupby, method)()

runtime = timeit.timeit(workload, number=1)

print("Mean:", runtime * 1000)
