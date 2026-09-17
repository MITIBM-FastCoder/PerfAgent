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
import dask.dataframe as dd

def setup():
    global ddf
    data = {}
    for i in range(10000):
        data["col"+str(i)] = [1.0] * 10
    df = pd.DataFrame(data)
    ddf = dd.from_pandas(df, npartitions=1)

def workload():
    global ddf
    dloc = ddf.loc[0]
    dmeta = ddf._meta_nonempty

runtime = timeit.timeit(workload, number=1, setup=setup)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
