
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

N = 10 ** 5
values = list("a" * N + "b" * N + "c" * N)
indices = {
    "monotonic_incr": pd.CategoricalIndex(values),
    "monotonic_decr": pd.CategoricalIndex(reversed(values)),
    "non_monotonic": pd.CategoricalIndex(list("abc" * N)),
}

int_scalar = 10000
int_list = list(range(10000))

def workload():
    for data in indices.values():
        data[: int_scalar]

runtime = timeit.timeit(workload, number=1)

print("Mean:", runtime * 1000)
