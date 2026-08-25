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
import xarray as xr
import sys
import os

# silence command-line output temporarily
sys.stdout, sys.stderr = os.devnull, os.devnull

def setup():
    global ds0
    
    a = np.arange(0, 2000)
    data_vars = dict()
    for i in a:
        data_vars[f"long_variable_name_{i}"] = xr.DataArray(
            name=f"long_variable_name_{i}",
            data=np.arange(0, 20),
            dims=[f"long_coord_name_{i}_x"],
            coords={f"long_coord_name_{i}_x": np.arange(0, 20) * 2},
        )
    ds0 = xr.Dataset(data_vars)
    ds0.attrs = {f"attr_{k}": 2 for k in a}

def workload():
    global ds0
    print(ds0)
    
# unsilence command-line output
sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__

runtime = timeit.timeit(workload, number=1, setup=setup)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
 