

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

N = 4000

def setup():
    global arrays, names
    arrays = [
        np.arange(5)
        for i in range(N)
    ]

    names = [
        'field_{}'.format(i)
        for i in range(N)
    ]
 
def workload():
    global arrays, names
    arr = np.core.records.fromarrays(arrays, names=names)

runtime = timeit.timeit(workload, number=1, setup=setup)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
