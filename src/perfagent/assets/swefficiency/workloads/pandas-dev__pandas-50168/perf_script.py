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

dates = pd.date_range('1900', '2000').tz_localize('+01:00').strftime('%Y-%d-%m %H:%M:%S%z').tolist()
dates.append('2020-01-01 00:00:00+02:00')

def workload():
    pd.to_datetime(dates, format='%Y-%d-%m %H:%M:%S%z')
    
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
