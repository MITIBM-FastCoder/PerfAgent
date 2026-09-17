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


dtype_combos = [
    (("float64", "float64[pyarrow]"), False),
    (("float64", "Float64"), False),
    (("int64[pyarrow]", "float64[pyarrow]"), False),
    (("int64[pyarrow]", "float64[pyarrow]"), True),
    (("float64", "Float64"), True),
    (("Int64", "Float64"), False),
    (("Int64", "Float64"), True),
    (("float64", "float64[pyarrow]"), True),
    (("Float64", "Float64"), True),
    (("float64[pyarrow]", "float64[pyarrow]"), True),
    (("Float64", "Float64"), False),
    (("float64[pyarrow]", "float64[pyarrow]"), False),
]

astype_registry = []

for (from_dtype, to_dtype), copy in dtype_combos:
    if from_dtype.startswith("float") or from_dtype in ("Float64",):
        data = np.random.randn(100, 100)
    elif from_dtype.startswith("int") or from_dtype in ("Int64",):
        data = np.random.randint(0, 1000, size=(100, 100))
    else:
        continue

    df = pd.DataFrame(data, dtype=from_dtype)
    astype_registry.append((df, to_dtype, copy))

def workload():
    for df, to_dtype, copy in astype_registry:
        df.astype(to_dtype, copy=copy)

runtime = timeit.timeit(workload, number=1)

# Print runtime mean and std deviation.
print("Mean:", runtime * 1000)

