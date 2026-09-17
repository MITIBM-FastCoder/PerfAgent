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

categories = [f"cat_{i:03}" for i in range(1000)]

idx1 = pd.CategoricalIndex(np.repeat(categories, 1000), categories=categories)
idx2 = pd.CategoricalIndex(categories[100:200], categories=reversed(categories))

df1 = pd.DataFrame({"val1": 1}, index=idx1)
df2 = pd.DataFrame({"val2": 2}, index=idx2)

def workload():
    df1.join(df2)
    
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
