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

lev = pd.Index(list("ABCDEFGHIJ"))
ri = pd.Index(range(1000))
mi = pd.MultiIndex.from_product([lev, ri], names=["foo", "bar"])

index = pd.date_range("2016-01-01", periods=10000, freq="s", tz="US/Pacific")
index = index.tz_localize(None).to_period("s")

ser = pd.Series(index, index=mi)
df = ser.unstack("bar")

def workload():
    ser.unstack("bar")
    
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
