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
import xarray as xr

m = 100_000
i1 = np.repeat([1, 2, 3, 4], m) 
i2 = np.tile(np.arange(m), 4)
d3 = np.random.randint(0, 2, 4 * m).astype(bool)

ds = xr.Dataset(
    data_vars=dict(
        d3=("row", d3)  
    ),
    coords=dict(
        i1=("row", i1), 
        i2=("row", i2)
    ),
)
ds = ds.set_index(row=["i1", "i2"]).rename({"row": "index"})

def workload():
    ds.assign(foo=~ds["d3"])

runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
