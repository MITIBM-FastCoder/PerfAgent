import argparse
import os
import json
import random
import re
import subprocess
import timeit
import shlex
import sys
import tempfile

from typing import List, Optional, Tuple

# Matches the official GSO eval protocol (harness MAX_ITERS): 5 fresh-process
# timing runs per measurement, 1 for heavy repos (llama-cpp, onnxruntime,
# tokenizers) — run_instance.py sets this env var per repo.
TIMING_ITERS = max(1, int(os.environ.get("GSO_TIMING_ITERS", "5")))

def extract_execution_time(stdout: str) -> Optional[float]:
    """Return the last 'Execution time' value printed by the perf script (already in ms)."""
    runtime_line = None
    for line in stdout.splitlines():
        if "Execution time" in line:
            runtime_line = line
    if runtime_line is None:
        return None
    return float(runtime_line.split(":")[1])

def run_prob_script(prob_script: str, no_eqcheck: bool = False) -> Tuple[str, bool]:
    run_test_cmd = f"python {prob_script}"
    if no_eqcheck:
        run_test_cmd += " --no-eqcheck"
    result = subprocess.run(shlex.split(run_test_cmd), cwd="/", capture_output=True, text=True)

    if result.returncode != 0:
        error_output = f"error running script: /{prob_script}\n. Output: {result.stdout}\n{result.stderr}\n"
        return error_output, False

    return "", True

def run_prob_script_reference(prob_script: str):
    run_test_cmd = f"python {prob_script} --reference"
    result = subprocess.run(shlex.split(run_test_cmd), cwd="/", capture_output=True, text=True)

    assert result.returncode == 0, f"profiler should not have errored on reference for test script: {prob_script}. result: {result}, stdout: {result.stdout}\nstderr: {result.stderr}"

def time_prob_script(prob_script: str, no_eqcheck: bool = False, iters: int = TIMING_ITERS) -> List[float]:
    """Time the perf script the official GSO way: `iters` fresh-process runs,
    no profiler attached. Returns the per-run times in ms (caller averages)."""
    run_test_cmd = f"python {prob_script}"
    if no_eqcheck:
        run_test_cmd += " --no-eqcheck"
    times = []
    for _ in range(iters):
        result = subprocess.run(shlex.split(run_test_cmd), cwd="/", capture_output=True, text=True)

        assert result.returncode == 0, f"timing run should not have errored after the validation run passed for test script: {prob_script}. stdout: {result.stdout}\nstderr: {result.stderr}"

        execution_time = extract_execution_time(result.stdout)
        assert execution_time is not None, f"runtime not found in timing run for test script: {prob_script}, stdout:\n{result.stdout}\nstderr: {result.stderr}"
        times.append(execution_time)
    return times

def save_pyspy_log(result) -> None:
    """Keep py-spy's own messages when PYSPY_LOG_FILE is set (tools/profiler_smoke.py does this,
    together with RUST_LOG=warn, to see how many samples py-spy dropped and why). Never set during
    agent runs."""
    log_file = os.environ.get("PYSPY_LOG_FILE")
    if log_file:
        with open(log_file, "w") as f:
            f.write(result.stdout + result.stderr)

def strip_pyspy_lines(text: str) -> str:
    """Drop py-spy's own chatter ("py-spy> ...") from the parser output. Every report line is kept,
    including function names that happen to contain "Error"."""
    return "\n".join(line for line in text.splitlines() if "py-spy>" not in line)

def profile_prob_script(prob_script: str, no_eqcheck: bool = False) -> str:
    # --idle keeps samples of the main thread while it waits on work done by native helper threads
    # (Arrow, OpenBLAS, rayon pools). py-spy cannot see those threads, and without --idle it would drop
    # the sample entirely, so the wall time inside experiment() would go unattributed.
    profile_cmd = f"py-spy record --idle -f raw -o profile.folded -- python {prob_script}"
    if no_eqcheck:
        profile_cmd += " --no-eqcheck"
    result = subprocess.run(shlex.split(profile_cmd), cwd="/", capture_output=True, text=True)
    save_pyspy_log(result)
    if result.returncode != 0:
        if "No child processes" not in result.stdout and "No child processes" not in result.stderr:
            raise RuntimeError(f"profiler should not have errored after having already run the test script! stdout: {result.stdout}\nstderr: {result.stderr}")

    # The profiled run must have completed for profile.folded to be valid. Its
    # timing is discarded: py-spy sampling overhead inflates it, so the
    # reported runtime comes from a separate standalone run instead.
    assert extract_execution_time(result.stdout) is not None, f"runtime not found in test script: {prob_script}, stdout:\n{result.stdout}\nstderr: {result.stderr}"

    parse_profile_cmd = "python parse_pyspy.py profile.folded"
    # parse_profile_cmd = "python parse_pyspy_enhanced.py profile.folded --report json"
    result = subprocess.run(shlex.split(parse_profile_cmd), cwd="/", capture_output=True, text=True)
    assert result.returncode == 0, f"parsing profile should never fail. stdout: {result.stdout}\nstderr: {result.stderr}"

    return strip_pyspy_lines(result.stdout)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Measure performance of test scripts.")
    parser.add_argument(
        "--reference",
        action="store_true",
        help="Store result as reference instead of comparing",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help=(
            "Profile perf_script.py with --no-eqcheck. Use only for temporary "
            "counterfactual probes; final verification must use strict mode."
        ),
    )
    args = parser.parse_args()
    if args.reference and args.probe:
        parser.error("--probe cannot be combined with --reference")

    prob_script_fname = "perf_script.py"
    if args.reference:
        run_prob_script_reference(prob_script_fname)
    else:
        output, success = run_prob_script(prob_script_fname, no_eqcheck=args.probe)
        if not success:
            print(output)
            sys.exit(1)

    profiler_body = profile_prob_script(prob_script_fname, no_eqcheck=args.probe)
    times = time_prob_script(prob_script_fname, no_eqcheck=args.probe)
    runtime = sum(times) / len(times)
    samples = ", ".join(f"{t:.3f}" for t in times)

    print(f"_runtime: {runtime}")
    print(f"""
<profiler_output>
Profiler output for {prob_script_fname}, runtime: {runtime:.6f}ms (mean of {len(times)} standalone runs: [{samples}])

{profiler_body}
</profiler_output>
""")

if __name__ == "__main__":
    main()
