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
from astropy.table.column import MaskedColumn

def setup():
    global dat
    dat = np.arange(1e7)

def workload():
    global dat
    _ = MaskedColumn(dat)
    
runtime = timeit.timeit(workload, number=1, setup = setup)

print("Mean:", runtime * 1000)
