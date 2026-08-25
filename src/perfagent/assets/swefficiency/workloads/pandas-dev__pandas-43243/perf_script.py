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

ngroups = 1000
ncols = 2
size = ngroups * 2
rng = np.arange(ngroups).reshape(-1, 1)
rng = np.broadcast_to(rng, (len(rng), ncols))
taker = np.random.randint(0, ngroups, size=size)
values = rng.take(taker, axis=0)
key = np.random.randint(0, size, size=size)

cols = [f"values{n}" for n in range(ncols)]
df = pd.DataFrame(values, columns=cols)
df["key"] = key

def workload():
    df.groupby("key")[cols].skew()

runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
