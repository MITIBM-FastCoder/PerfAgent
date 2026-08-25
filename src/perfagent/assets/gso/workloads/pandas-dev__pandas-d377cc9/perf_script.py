import pandas as pd
import numpy as np
import timeit
import json
import os

def setup():
    np.random.seed(42)
    unique_values = np.arange(30000, dtype=np.int64)
    data = np.random.choice(unique_values, size=1000000)
    df = pd.DataFrame({'A': data, 'B': data % 100})
    return df

def experiment(df):
    result = df.groupby('A').nunique()
    return result

def store_result(result, filename):
    result_dict = {'index': result.index.tolist(), 'B': result['B'].tolist()}
    with open(filename, 'w') as f:
        json.dump(result_dict, f)

def load_result(filename):
    with open(filename, 'r') as f:
        result_dict = json.load(f)
    index = pd.Index(result_dict['index'])
    data = {'B': result_dict['B']}
    return pd.DataFrame(data, index=index)

def check_equivalence(reference_result, current_result):
    assert reference_result.equals(current_result), 'Results do not match!'

def run_test(eqcheck: bool=False, reference: bool=False, prefix: str='') -> float:
    df = setup()
    execution_time, result = timeit.timeit(lambda: experiment(df), number=1)
    if reference:
        store_result(result, f'{prefix}_result.json')
    if eqcheck:
        reference_result = load_result(f'{prefix}_result.json')
        check_equivalence(reference_result, result)
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
