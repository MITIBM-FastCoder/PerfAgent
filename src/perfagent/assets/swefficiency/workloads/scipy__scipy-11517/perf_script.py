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

import scipy
from numpy import ones, array, asarray, empty, random
from scipy.sparse import dia_matrix

def poisson2d(N, dtype='d', format=None):
    if N == 1:
        diags = asarray([[4]], dtype=dtype)
        return dia_matrix((diags, [0]), shape=(1, 1)).asformat(format)

    offsets = array([0, -N, N, -1, 1])

    diags = empty((5, N**2), dtype=dtype)

    diags[0] = 4  
    diags[1:] = -1  

    diags[3, N-1::N] = 0  
    diags[4, N::N] = 0  

    return dia_matrix((diags, offsets), shape=(N**2, N**2)).asformat(format)

base_format = "lil"
base = poisson2d(100, format=base_format)
to_formats = ["dok", "dia", "csr", "bsr", "coo"]
conversion_lambdas = [
    getattr(base, 'to' + to_format) for to_format in to_formats
]

def workload():
    for convert in conversion_lambdas:
        _ = convert()

runtime = timeit.timeit(workload, number=1)

print("Mean:", runtime * 1000)
