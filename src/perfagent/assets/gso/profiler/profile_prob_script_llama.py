from __future__ import annotations

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
import time
from pathlib import Path

from typing import Tuple

REFERENCE_TIMING_FILE = "/reference_timing.json"
OPTIMIZED_TIMING_FILE = "/optimized_timing.json"
PROFILE_FOLDED_FILE = "/profile.folded"
PROFILE_MAPS_FILE = "/profile.maps"
PROFILE_STDOUT_FILE = "/profile_target.stdout"
PROFILE_STDERR_FILE = "/profile_target.stderr"

# Matches the official GSO eval protocol (harness MAX_ITERS): llama-cpp is in
# the heavy-repo list timed with a single fresh-process run.
TIMING_ITERS = max(1, int(os.environ.get("GSO_TIMING_ITERS", "1")))


def extract_execution_time(stdout: str) -> float | None:
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


def time_prob_script(prob_script: str, no_eqcheck: bool = False, iters: int = TIMING_ITERS) -> list[float]:
    """Time the perf script the official GSO way: `iters` fresh-process runs,
    no profiler attached. Returns the per-run times in ms (caller averages)."""
    run_test_cmd = f"python {prob_script}"
    if no_eqcheck:
        run_test_cmd += " --no-eqcheck"
    times = []
    for _ in range(iters):
        result = subprocess.run(shlex.split(run_test_cmd), cwd="/", capture_output=True, text=True)

        assert result.returncode == 0, (
            f"timing run should not have errored after the validation run passed for test script: "
            f"{prob_script}. stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        execution_time = extract_execution_time(result.stdout)
        assert execution_time is not None, (
            f"runtime not found in timing run for test script: {prob_script}, "
            f"stdout:\n{result.stdout}\nstderr: {result.stderr}"
        )
        times.append(execution_time)
    return times


def _capture_process_maps(
    pid: int,
    output_path: str,
    *,
    wait_for_substrings: tuple[str, ...] = (),
    timeout_s: float = 0.0,
    poll_interval_s: float = 0.05,
) -> None:
    maps_path = Path(f"/proc/{pid}/maps")
    deadline = time.monotonic() + timeout_s
    latest_maps = None

    while maps_path.exists():
        latest_maps = maps_path.read_text()
        if not wait_for_substrings or any(
            needle in latest_maps for needle in wait_for_substrings
        ):
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_interval_s)

    if latest_maps is not None:
        Path(output_path).write_text(latest_maps)


def _profile_by_pid(
    prob_script: str,
    no_eqcheck: bool = False,
) -> tuple[subprocess.CompletedProcess[str], str, str, int]:
    stdout_path = Path(PROFILE_STDOUT_FILE)
    stderr_path = Path(PROFILE_STDERR_FILE)
    for path in [Path(PROFILE_FOLDED_FILE), Path(PROFILE_MAPS_FILE), stdout_path, stderr_path]:
        if path.exists():
            path.unlink()

    with stdout_path.open("w") as stdout_file, stderr_path.open("w") as stderr_file:
        child = subprocess.Popen(
            ["python", prob_script] + (["--no-eqcheck"] if no_eqcheck else []),
            cwd="/",
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
        )

        _capture_process_maps(
            child.pid,
            PROFILE_MAPS_FILE,
            wait_for_substrings=("libllama.so", "libggml", "llama_cpp"),
            timeout_s=10.0,
        )
        profile_result = subprocess.run(
            [
                "py-spy",
                "record",
                "--native",
                "-f",
                "raw",
                "-o",
                PROFILE_FOLDED_FILE,
                "--pid",
                str(child.pid),
            ],
            cwd="/",
            capture_output=True,
            text=True,
        )
        child_returncode = child.wait()

    return (
        profile_result,
        stdout_path.read_text() if stdout_path.exists() else "",
        stderr_path.read_text() if stderr_path.exists() else "",
        child_returncode,
    )


def profile_prob_script(prob_script: str, no_eqcheck: bool = False) -> str:
    result, script_stdout, script_stderr, child_returncode = _profile_by_pid(
        prob_script,
        no_eqcheck=no_eqcheck,
    )

    if child_returncode != 0:
        raise RuntimeError(
            f"error running profiled script: /{prob_script}\nstdout: {script_stdout}\nstderr: {script_stderr}"
        )

    if result.returncode != 0:
        if "No child processes" not in result.stdout and "No child processes" not in result.stderr:
            raise RuntimeError(
                f"profiler should not have errored after having already run the test script! "
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

    # The profiled run must have completed for profile.folded to be valid. Its
    # timing is discarded: py-spy sampling overhead inflates it, so the
    # reported runtime comes from a separate standalone run instead.
    assert extract_execution_time(script_stdout) is not None, (
        f"runtime not found in test script: {prob_script}, "
        f"stdout:\n{script_stdout}\nstderr: {script_stderr}"
    )

    parse_profile_cmd = "python parse_pyspy.py profile.folded --maps profile.maps"
    result = subprocess.run(shlex.split(parse_profile_cmd), cwd="/", capture_output=True, text=True)
    assert result.returncode == 0, f"parsing profile should never fail. stdout: {result.stdout}\nstderr: {result.stderr}"

    filtered_lines = []
    for line in result.stdout.splitlines():
        if "py-spy>" in line or "Error" in line:
            continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines)


def main():
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
    runs_note = f"(mean of {len(times)} standalone runs: [{samples}])"

    if args.reference:
        timing_results_path = REFERENCE_TIMING_FILE
        header = f"Profiler output for {prob_script_fname}, runtime: {runtime:.6f}ms {runs_note}"
    else:
        timing_results_path = OPTIMIZED_TIMING_FILE
        if os.path.exists(OPTIMIZED_TIMING_FILE):
            os.remove(OPTIMIZED_TIMING_FILE)
        with open(REFERENCE_TIMING_FILE, "r") as f:
            reference_timing_info = json.load(f)
        reference_time = reference_timing_info[prob_script_fname]
        speedup = reference_time / runtime
        header = (
            f"Profiler output for {prob_script_fname}, optimized runtime: {runtime:.6f}ms {runs_note}, "
            f"baseline runtime: {reference_time:.6f}ms, speedup: {speedup:.6f}"
        )

    with open(timing_results_path, "w") as f:
        json.dump({prob_script_fname: runtime}, f, indent=2)

    print(f"_runtime: {runtime}")
    print(f"""
<profiler_output>
{header}

{profiler_body}
</profiler_output>
""")


if __name__ == "__main__":
    main()
