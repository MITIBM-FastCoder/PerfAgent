import pandas as pd
import numpy as np
import json
import timeit
import os

def setup():
    np.random.seed(42)
    size = 10 ** 6
    arr = pd.array(np.arange(size), dtype='Int64')
    return arr

def experiment(data):
    arr = data.copy()
    n_updates = 10000
    n = len(arr)
    for i in range(n_updates):
        idx = i % n
        arr[idx] = i
    return int(arr.sum())

def store_result(result, filename):
    data = {'result': result}
    with open(filename, 'w') as f:
        json.dump(data, f)

def load_result(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    return data['result']

def check_equivalence(reference_result, current_result):
    assert reference_result == current_result, f'Reference result ({reference_result}) does not match current result ({current_result}).'

def run_test(eqcheck: bool=False, reference: bool=False, prefix: str='') -> float:
    data = setup()
    execution_time, result = timeit.timeit(lambda: experiment(data), number=1)
    filename = f'{prefix}_result.json' if prefix else 'reference_result.json'
    if reference:
        store_result(result, filename)
    if eqcheck:
        ref_result = load_result(filename)
        check_equivalence(ref_result, result)
    return execution_time

timeit.template = """
def inner(_it, _timer{init}):
    {setup}
    _profile_duration = 10.0

    _t0 = _timer()
    retval = {stmt}
    _t1 = _timer()

    _first_time = _t1 - _t0

    if _first_time >= _profile_duration:
        return _first_time, retval

    _profile_start = _timer()
    while _timer() - _profile_start < _profile_duration:
        retval = {stmt}

    return _first_time, retval
"""

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Measure performance of API.")
    parser.add_argument(
        "--reference",
        action="store_true",
        help="Store result as reference instead of comparing",
    )
    parser.add_argument(
        "--no-eqcheck",
        action="store_true",
        help="Run timing without comparing against the stored reference result.",
    )
    args = parser.parse_args()

    # Measure the execution time
    execution_time = run_test(not args.no_eqcheck, args.reference, os.path.splitext(os.path.basename(__file__))[0])
    # Print the execution time
    print(f"Execution time: {execution_time * 1000:.6f}")


if __name__ == "__main__":
    main()
