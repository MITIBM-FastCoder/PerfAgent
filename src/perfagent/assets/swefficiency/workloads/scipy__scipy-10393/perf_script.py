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
from numpy.random import rand
from numpy import arange, asarray, zeros, dot, exp, pi, double, cdouble
import numpy as np
import scipy.fft as scipy_fft

np.random.seed(0)

def random(size):
    return rand(*size)

def setup():
    global func, x
    x = random([313]).astype(cdouble)+random([313]).astype(cdouble)*1j
    module = scipy_fft
    func = getattr(module, 'fft')
    
def workload():
    global func, x
    func(x)

runtime = timeit.timeit(workload, number=1, setup=setup)

print("Mean:", runtime * 1000)
