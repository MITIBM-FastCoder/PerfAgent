import pandas as pd
import numpy as np
import timeit
import json

def setup():
    np.random.seed(42)
    num_rows = 100000
    data = {'string_col': np.random.choice(['apple', 'banana', 'cherry', 'date'], size=num_rows), 'float_col': np.random.rand(num_rows) * 1000, 'int_col': np.random.randint(0, 100, size=num_rows)}
    df = pd.DataFrame(data)
    return df

def experiment(df):
    string_array = df['string_col'].to_numpy()
    result = pd._libs.lib.ensure_string_array(string_array)
    return result

def store_result(result, filename):
    result_list = result.tolist()
    with open(filename, 'w') as f:
        json.dump(result_list, f)

def load_result(filename):
    with open(filename, 'r') as f:
        result_list = json.load(f)
    return np.array(result_list, dtype=object)

def check_equivalence(reference_result, current_result):
    assert reference_result.shape == current_result.shape, 'Shapes do not match'
    assert np.array_equal(reference_result, current_result), 'Arrays are not equal'

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
