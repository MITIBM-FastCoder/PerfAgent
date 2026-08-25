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

import sklearn
import sklearn.metrics
import numpy as np

import itertools

dtype = "int64"
n_inputs = [1000, 10000, 200000]
n_classes = [10, 100, 1000]

def make_inputs(n_input, n_classes, dtype=dtype, rng=np.random):
    y_true = (rng.rand(n_input) * n_classes).astype(dtype)
    y_pred = (rng.rand(n_input) * n_classes).astype(dtype)

    return y_true, y_pred

work = []
for n_input, n_class in itertools.product(n_inputs, n_classes):
    work.append(make_inputs(n_input, n_class))

def workload():
    for e in work:
        sklearn.metrics.confusion_matrix(*e)
        
runtime = timeit.timeit(workload, number=1)

print("Mean:", runtime * 1000)
