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

methods = ["any", "all"]

ngroups = 1000
ncols = 10
size = ngroups * 2
rng = np.arange(ngroups).reshape(-1, 1)
rng = np.broadcast_to(rng, (len(rng), ncols))
taker = np.random.randint(0, ngroups, size=size)
values = rng.take(taker, axis=0)
key = np.concatenate(
    [np.random.random(ngroups) * 0.1, np.random.random(ngroups) * 10.0]
)

cols = [f"values{n}" for n in range(ncols)]
df = pd.DataFrame(values, columns=cols)
df["key"] = key

def workload():
    for method in methods:
        df.groupby("key")[cols].transform(method)
        getattr(df.groupby("key")[cols], method)

runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
