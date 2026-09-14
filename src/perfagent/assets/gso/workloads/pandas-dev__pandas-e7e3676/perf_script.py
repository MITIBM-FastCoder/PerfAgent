import numpy as np
import pandas as pd
import timeit
import json
import os

def setup():
    N = 500000
    cols = 500
    df = pd.DataFrame(np.random.rand(N, cols))
    return df

def experiment(df):
    df[100] = 100
    df[[200, 300, 400]] = 200
    return df

def store_result(result, filename):
    data_dict = {'column_100': result[100].tolist(), 'columns_200_300_400': result[[200, 300, 400]].values.tolist()}
    with open(filename, 'w') as f:
        json.dump(data_dict, f)

def load_result(filename):
    with open(filename, 'r') as f:
        data_dict = json.load(f)
    return data_dict

def check_equivalence(reference, current):
    assert reference['column_100'] == current[100].tolist()
    assert reference['columns_200_300_400'] == current[[200, 300, 400]].values.tolist()

def run_test(eqcheck: bool=False, reference: bool=False, prefix: str='') -> float:
    _state = {}
    def _fresh_setup():
        _state["df"] = setup()
    execution_time, result = timeit.timeit(lambda: experiment(_state["df"]), setup=_fresh_setup, number=1)
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

    # experiment() is not idempotent for this workload (see perfagent README, "Profiling loop"):
    # rebuild its input before every repeat so the profile matches the timed first call.
    _profile_start = _timer()
    while _timer() - _profile_start < _profile_duration:
        {setup}
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
