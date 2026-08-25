
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
idx = pd.date_range(start="1/1/2000", periods=N, freq="s")
s = pd.Series(np.random.randn(N), index=idx)

def workload():
    s.sort_index()

runtime = timeit.timeit(workload, number=1)

print("Mean:", runtime * 1000)
