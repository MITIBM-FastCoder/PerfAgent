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

n1 = 10 ** 7
n2 = 10

lev0 = pd.date_range("2000-01-01", "2020-12-31", freq="D")
lev1 = np.arange(10000)
mi = pd.MultiIndex.from_product([lev0, lev1])

df = pd.DataFrame({"A": 1.0}, index=mi)

def workload():
    df.loc["2010-12-31": "2015-12-31"]

runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
