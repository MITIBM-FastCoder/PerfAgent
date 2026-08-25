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

dfs = []

for factor in [4, 5]:
    N = 10 ** factor
    labels = np.random.randint(0, 2000 if factor == 4 else 20, size=N)
    labels2 = np.random.randint(0, 3, size=N)
    df = pd.DataFrame(
        {
            "key": labels,
            "key2": labels2,
            "value1": np.random.randn(N),
            "value2": ["foo", "bar", "baz", "qux"] * (N // 4),
        }
    )
    dfs.append(df)

def df_copy_function(g):
    g.name
    return g.copy()

def workload():
    for df in dfs:
        df.groupby("key").apply(df_copy_function)

runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
