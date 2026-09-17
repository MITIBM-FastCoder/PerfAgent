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

import dask.dataframe as dd
from dask.utils import parse_bytes
from dask.sizeof import sizeof
from dask.datasets import timeseries
import pandas as pd

def timeseries_of_size(
    target_nbytes,
    *,
    start="2000-01-01",
    freq="1s",
    partition_freq="1d",
    dtypes={"name": str, "id": int, "x": float, "y": float},
    seed=None,
    **kwargs,
):
    if isinstance(target_nbytes, str):
        target_nbytes = parse_bytes(target_nbytes)

    start_dt = pd.to_datetime(start)
    partition_freq_dt = pd.to_timedelta(partition_freq)

    example_part = timeseries(
        start=start,
        end=start_dt + partition_freq_dt,
        freq=freq,
        partition_freq=partition_freq,
        dtypes=dtypes,
        seed=seed,
        **kwargs,
    )
    p = example_part.compute(scheduler="threads")
    partition_size = sizeof(p)
    npartitions = round(target_nbytes / partition_size)

    ts = timeseries(
        start=start,
        end=start_dt + partition_freq_dt * npartitions,
        freq=freq,
        partition_freq=partition_freq,
        dtypes=dtypes,
        seed=seed,
        **kwargs,
    )
    return ts


def setup():
    global df, df2
    df  = timeseries_of_size("1GB", start="2020-01-01",
                             freq="600ms", partition_freq="12h",
                             dtypes={str(i): float for i in range(100)})

    df2 = timeseries_of_size("512MB", start="2010-01-01",
                             freq="600ms", partition_freq="12h",
                             dtypes={str(i): float for i in range(100)})


def workload():
    # Force alignment, then reduction, then materialise the result
    (df2 - df).mean().compute()

runtime = timeit.timeit(workload, number=1, setup=setup)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
