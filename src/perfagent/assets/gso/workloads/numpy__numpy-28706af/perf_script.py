import argparse
import os
import numpy as np
import timeit

def setup():
    np.random.seed(42)
    a = np.random.rand(1000000).astype(np.float64) + 1.0
    indices = np.random.randint(0, a.size, size=500000, dtype=np.intp)
    divisors = np.random.rand(500000).astype(np.float64) + 0.5
    return {'a': a, 'indices': indices, 'divisors': divisors}

def experiment(workload):
    a = workload['a']
    indices = workload['indices']
    divisors = workload['divisors']
    np.divide.at(a, indices, divisors)
    return a

def store_result(result, filename):
    np.save(filename, result)

def load_result(filename):
    return np.load(filename, allow_pickle=False)

def check_equivalence(reference_result, current_result):
    assert reference_result.shape == current_result.shape, 'Shape mismatch between reference and current results.'
    if not np.allclose(reference_result, current_result, rtol=1e-05, atol=1e-08):
        raise AssertionError('Numerical values of the arrays differ beyond acceptable tolerance.')

def run_test(eqcheck: bool=False, reference: bool=False, prefix: str='') -> float:
    _state = {}
    def _fresh_setup():
        _state["workload"] = setup()
    execution_time, result = timeit.timeit(lambda: experiment(_state["workload"]), setup=_fresh_setup, number=1)
    filename = f'{prefix}_result.npy' if prefix else 'reference_result.npy'
    if reference:
        store_result(result, filename)
    if eqcheck:
        reference_result = load_result(filename)
        check_equivalence(reference_result, result)
    return execution_time

timeit.template = """
def inner(_it, _timer{init}):
    {setup}
    _profile_duration = 60.0

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
