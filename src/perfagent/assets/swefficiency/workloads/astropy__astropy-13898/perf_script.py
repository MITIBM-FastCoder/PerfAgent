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
import astropy.io.fits
import numpy as np
from astropy.visualization.interval import ManualInterval

np.random.seed(0)

def setup():
    global interval, data
    
    interval = ManualInterval(vmin=0.1, vmax=0.9)
    data = np.random.uniform(0, 1, size=10000)
    
def workload():
    global interval, data
    interval.get_limits(data)

runtime = timeit.timeit(workload, number=1, setup=setup)

print("Mean:", runtime * 1000)
