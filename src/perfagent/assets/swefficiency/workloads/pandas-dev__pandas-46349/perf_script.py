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

import numpy as np
import pandas as pd

from itertools import permutations, chain
import string

string_values = chain(
    string.ascii_uppercase,
    permutations(string.ascii_uppercase, 2),
    permutations(string.ascii_uppercase, 3),
)

string_index = pd.Index(map(''.join, string_values)).astype('string')

df = pd.DataFrame({'ints': range(len(string_index))}, index=string_index)

subset_index = string_index[string_index.str.startswith('A')]

def workload():
    df.loc[subset_index]
    
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
