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
import string

m = 100
n = 50

levels = np.arange(m)
index = pd.MultiIndex.from_product([levels] * 2)
columns = np.arange(n)

indices = np.random.randint(0, 52, size=(m * m, n))
values = np.take(list(string.ascii_letters), indices)
values = [pd.Categorical(v) for v in values.T]

df = pd.DataFrame(
    {i: cat for i, cat in enumerate(values)}, index, columns
)

def workload():
    df.unstack()

runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
