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

from scipy.optimize._linprog_util import _presolve, _clean_inputs, _LPProblem
from scipy.sparse import csr_matrix
import numpy as np
import os

meth = "sparse"
prob = "80BAU3B"

dir_path = "/testbed/benchmarks/benchmarks"
datafile = os.path.join(dir_path, "linprog_benchmark_files",
                        prob + ".npz")
data = np.load(datafile, allow_pickle=True)

c, A_eq, A_ub, b_ub, b_eq = (data["c"], data["A_eq"], data["A_ub"],
                                data["b_ub"], data["b_eq"])
bounds = np.squeeze(data["bounds"])
x0 = np.zeros(c.shape)

A_eq = csr_matrix(A_eq)
A_ub = csr_matrix(A_ub)

def setup():
    global lp_cleaned
    lp = _LPProblem(c, A_ub, b_ub, A_eq, b_eq, bounds, x0)
    lp_cleaned = _clean_inputs(lp)

def workload():
    global lp_cleaned
    _presolve(lp_cleaned, rr=False, tol=1e-9)

runtime = timeit.timeit(workload, number=1, setup=setup)

print("Mean:", runtime * 1000)
