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
from matplotlib.transforms import Affine2D
import numpy as np

def setup():
    global mtx, theta, aff
    mtx = np.array([[.1, .2, .3], [.4, .5, .6], [0, 0, 1]])
    theta = np.pi / 4
    aff = Affine2D()
    aff.set_matrix(mtx)

def workload():
    global mtx, theta, aff
    aff.rotate(theta)
    
runtimes = timeit.repeat(workload, number=1, repeat=1, setup=setup)
print("Mean:", statistics.mean(runtimes) * 1000)
