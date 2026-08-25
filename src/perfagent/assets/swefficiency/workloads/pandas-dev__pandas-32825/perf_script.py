
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

import pandas as pd
import scipy.sparse

n_samples = 100
n_features = 1000
X = scipy.sparse.rand(
    n_samples, n_features, random_state=0, density=0.01, format="csr"
)

def workload():
    pd.DataFrame.sparse.from_spmatrix(X)

runtime = timeit.timeit(workload, number=1)

print("Mean:", runtime * 1000)
