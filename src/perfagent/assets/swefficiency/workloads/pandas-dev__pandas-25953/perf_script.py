
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

ops = ['mean', 'sum', 'median', 'std', 'skew', 'kurt', 'mad', 'prod', 'sem',
       'var']
level = 1

levels = [np.arange(10), np.arange(100), np.arange(100)]
codes = [np.arange(10).repeat(10000),
            np.tile(np.arange(100).repeat(100), 10),
            np.tile(np.tile(np.arange(100), 100), 10)]
index = pd.MultiIndex(levels=levels, codes=codes)
s = pd.Series(np.random.randn(len(index)), index=index)

op_funcs = [getattr(s, op) for op in ops]

def workload():
    for op in op_funcs:
        op(level=level)

runtime = timeit.timeit(workload, number=1)

print("Mean:", runtime * 1000)
