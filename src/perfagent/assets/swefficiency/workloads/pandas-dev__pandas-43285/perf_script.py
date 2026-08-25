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
import numpy as np

cols = 36
rows = 12

def _apply_func(s):
    return [
        "background-color: lightcyan" if s.name == "row_1" else "" for v in s
    ]

def initialize():
    df = pd.DataFrame(
        np.random.randn(rows, cols),
        columns=[f"float_{i+1}" for i in range(cols)],
        index=[f"row_{i+1}" for i in range(rows)],
    )
    st = df.style.apply(_apply_func, axis=1)
    return st

initialize()

def workload():
    st = initialize()
    st._render_html(True, True)

runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
