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
import sympy
from sympy.matrices.dense import randMatrix
from sympy.polys.matrices import DomainMatrix
from sympy import I

def setup():
    global dM
    M = randMatrix(100) + randMatrix(100)*I/3
    dM = DomainMatrix.from_Matrix(M)

def workload():
    global dM
    _ = dM**2
    

runtime = timeit.timeit(workload, number=1, setup=setup)

print("Mean:", runtime * 1000)
