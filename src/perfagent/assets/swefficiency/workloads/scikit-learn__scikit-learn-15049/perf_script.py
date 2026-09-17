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

from scipy.sparse import random

from sklearn.metrics.pairwise import manhattan_distances

prova = random(2000, 1000, 0.001, "csr")

def workload():
    manhattan_distances(prova)
    
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
