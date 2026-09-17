import pandas as pd
import numpy as np
import timeit
import json

def setup():
    np.random.seed(42)
    n_rows = 10000
    n_cols = 10
    data = {f'col_{i}': np.random.choice([np.nan, 1, 2, 3, 'a', 'b', 'c'], n_rows) for i in range(n_cols)}
    df = pd.DataFrame(data)
    return df

def experiment(df):
    result = df.isna()
    return result

def store_result(result, filename):
    result_dict = {'columns': result.columns.tolist(), 'data': result.values.tolist()}
    with open(filename, 'w') as f:
        json.dump(result_dict, f)

def load_result(filename):
    with open(filename, 'r') as f:
        result_dict = json.load(f)
    df = pd.DataFrame(result_dict['data'], columns=result_dict['columns'])
    return df

def check_equivalence(reference_result, current_result):
    assert reference_result.shape == current_result.shape, 'Shapes do not match'
    assert (reference_result.columns == current_result.columns).all(), 'Columns do not match'
    assert (reference_result.values == current_result.values).all(), 'Data values do not match'

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
    import os
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
