
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

idx_large_fast = pd.RangeIndex(100_000)
idx_small_slow = pd.date_range(start="1/1/2012", periods=1)
mi_large_slow = pd.MultiIndex.from_product([idx_large_fast, idx_small_slow])

idx_non_object = pd.RangeIndex(1)

def workload():
    idx_non_object.equals(mi_large_slow)

runtime = timeit.timeit(workload, number=1)

print("Mean:", runtime * 1000)
