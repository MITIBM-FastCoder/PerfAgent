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
from sympy import Or
from sympy.abc import a, b, c, d, e, f, g, h, i
from sympy.logic.boolalg import simplify_logic
from sympy.core.cache import clear_cache

def setup():
    clear_cache()

def workload():
    _ = simplify_logic(Or(a,b,c,d,e,f,g,h,i))
    
runtime = timeit.timeit(workload, number=1, setup = setup)

print("Mean:", runtime * 1000)
