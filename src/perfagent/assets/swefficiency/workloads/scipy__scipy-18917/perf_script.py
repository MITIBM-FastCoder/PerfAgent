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

import scipy.signal

# Generate a large array to compute the spline on.
import numpy as np

data = np.random.rand(1000000)  # Adjust size as needed
    
def workload():
    scipy.signal.cspline1d(data)
    scipy.signal.qspline1d(data)

runtime = timeit.timeit(workload, number=1)

print("Mean:", runtime * 1000)
