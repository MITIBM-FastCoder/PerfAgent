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
from scipy.spatial import SphericalVoronoi

def setup():
    global points
    np.random.seed(0)
    num_points = 10000
    phi = np.random.uniform(0, 2 * np.pi, num_points)
    cos_theta = np.random.uniform(-1, 1, num_points)
    theta = np.arccos(cos_theta)
    x = np.sin(theta) * np.cos(phi)
    y = np.sin(theta) * np.sin(phi)
    z = np.cos(theta)
    points = np.column_stack((x, y, z))
    

def workload():
    global points
    sv = SphericalVoronoi(points)

runtime = timeit.timeit(workload, number=1, setup=setup)

print("Mean:", runtime * 1000)
