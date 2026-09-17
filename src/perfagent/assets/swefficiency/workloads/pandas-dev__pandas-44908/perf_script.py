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

n = 100_000
def setup():
    global df
    df = pd.DataFrame().assign(timestamp=pd.date_range('2000',  periods=n, freq='S'), col1=1).set_index('timestamp')

def workload():
    global df
    df.to_csv(date_format='%Y-%m-%d %H:%M:%S')
    
runtime = timeit.timeit(workload, number=1, setup=setup)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
