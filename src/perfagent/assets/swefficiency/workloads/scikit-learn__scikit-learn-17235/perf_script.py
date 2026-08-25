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

import sklearn.cluster
from sklearn import datasets

data = datasets.load_iris()['data']

def workload():
    sklearn.cluster.KMeans(n_clusters=2, init='k-means++', n_init=10).fit(data)
    
# Run benchmark
runtime = timeit.timeit(workload, number=1)

# Output results
print("Mean:", runtime * 1000)
