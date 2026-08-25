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

num_rows = 100
num_cols = 25_000
num_dfs = 7

def generate_dataframes(num_dfs, num_rows, num_cols, all_cols):
    df_list = []
    for i in range(num_dfs):
        index = ['i%d'%i for i in range(i*num_rows, (i+1)*num_rows)]
        columns = np.random.choice(all_cols, num_cols, replace=False)
        values = np.random.uniform(-100, 100, [num_rows, num_cols])
        df_list.append(pd.DataFrame(values, index=index, columns=columns))
    return df_list

num_all_cols = num_cols * num_dfs * 4 // 5
all_cols = ['c%i'%i for i in range(num_all_cols)]
df_list = generate_dataframes(num_dfs, num_rows, num_cols, all_cols)

def workload():
    pd.concat(df_list)
    
runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)
