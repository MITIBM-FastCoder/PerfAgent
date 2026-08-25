import itertools
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

params = [[12, 24, 36], [12, 120]]

dataframes = []
st = []

def _apply_func(s):
    return [
        "background-color: lightcyan" if s.name == "row_1" else "" for v in s
    ]

for cols, rows in itertools.product(*params):
    df = pd.DataFrame(
            np.random.randn(rows, cols),
            columns=[f"float_{i+1}" for i in range(cols)],
            index=[f"row_{i+1}" for i in range(rows)],
        )
    st.append(
        df.style.apply(_apply_func, axis=1)
    )
    
def workload():
    for elem in st:
        elem.render()


runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
