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

np.random.seed(0)

N = 100_000
data = np.arange(N) 
arr = pd.array(np.where(np.random.rand(N) > 0.1, data, np.nan), dtype="Int32")

def workload():
    arr._hash_pandas_object(encoding='utf-8', hash_key="1000000000000000", categorize=False)

runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
