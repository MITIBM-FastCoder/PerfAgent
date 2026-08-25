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

try:
    import pandas._testing as tm
except ImportError:
    import pandas.util.testing as tm

N = 10**5

dtypes = ("datetime", "int", "string", "ea_int")

level1 = range(1000)

level2 = pd.date_range(start="1/1/2000", periods=N // 1000)
dates_left = pd.MultiIndex.from_product([level1, level2])

level2 = range(N // 1000)
int_left = pd.MultiIndex.from_product([level1, level2])

level2 = tm.makeStringIndex(N // 1000).values
str_left = pd.MultiIndex.from_product([level1, level2])

level2 = range(N // 1000)
ea_int_left = pd.MultiIndex.from_product([level1, pd.Series(level2, dtype="Int64")])

data = {
    "datetime": dates_left,
    "int": int_left,
    "string": str_left,
    "ea_int": ea_int_left,
}
data_non_monotonic = {k: mi[::-1] for k, mi in data.items()}

data = {k: {"left": mi, "right": mi[:-1]} for k, mi in data.items()}
data_non_monotonic = {k: {"left": mi, "right": mi[:-1]} for k, mi in data_non_monotonic.items()}

def workload():
    for dtype in dtypes:
        data[dtype]['left'].union(data[dtype]['right'])
        data_non_monotonic[dtype]['left'].union(data_non_monotonic[dtype]['right'])
        
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
