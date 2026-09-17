
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

def setup():
    global df, df2, rng, grouper
    rng = pd.period_range(start='1/1/1990', freq='S', periods=20000)
    df = pd.DataFrame(index=range(len(rng)))

    N = 10**4
    grouper = pd.period_range('1900-01-01', freq='D', periods=N)
    df2 = pd.DataFrame(np.random.randn(10**4, 2))

def workload():
    global df, df2, rng, grouper
    df['col2'] = rng
    df.set_index('col2', append=True)
    
    df2.groupby(grouper).sum()

runtime = timeit.timeit(workload, number=1, setup=setup)

print("Mean:", runtime * 1000)
