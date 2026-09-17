import argparse
import os
import json
import subprocess
import shlex
import sys

from typing import Tuple

def time_workload(workload_script: str) -> Tuple[str, bool, float]:
    """Measure the workload runtime from a clean run with no profiler attached.

    py-spy sampling (especially --native) inflates and distorts wall time, so
    the runtime reported to the agent must never come from the instrumented run.
    """
    time_cmd = f"python {workload_script}"
    result = subprocess.run(shlex.split(time_cmd), cwd="/", stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if result.returncode != 0:
        return f"error running script:\n{result.stdout}\n{result.stderr}", False, 0.0

    runtime = None
    for line in result.stdout.splitlines():
        if "Mean" in line:
            runtime = line

    if runtime is None:
        return f"runtime not found in script: {workload_script}, stdout:\n{result.stdout}\nstderr: {result.stderr}", False, 0.0

    # workload scripts already report Mean in milliseconds
    return "", True, float(runtime.split(":")[1])

def profile_workload(workload_script: str) -> Tuple[str, bool]:
    profile_cmd = f"py-spy record --native -r 50 -f raw -o profile.folded -- python {workload_script}"
    result = subprocess.run(shlex.split(profile_cmd), cwd="/", stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if result.returncode != 0:
        if "No child processes" not in result.stdout and "No child processes" not in result.stderr:
            return f"error running script:\n{result.stdout}\n{result.stderr}", False

    parse_profile_cmd = "python parse_pyspy_compat.py profile.folded"
    # parse_profile_cmd = "python parse_pyspy.py profile.folded"
    # parse_profile_cmd = "python parse_pyspy_enhanced.py profile.folded --report json"
    result = subprocess.run(shlex.split(parse_profile_cmd), cwd="/", stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert result.returncode == 0, f"parsing profile should never fail. stdout: {result.stdout}\nstderr: {result.stderr}"

    filtered_lines = []
    for line in result.stdout.splitlines():
        if "py-spy>" in line or "Error" in line:
            continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines), True

def main():
    prob_script_fname = "perf_script.py"

    timing_output, success, runtime = time_workload(prob_script_fname)
    if not success:
        print(timing_output)
        sys.exit(1)

    profile_output, success = profile_workload(prob_script_fname)
    if not success:
        print(profile_output)
        sys.exit(1)

    print(f"_runtime: {runtime}")
    print(f"""
<profiler_output>
Profiler output for {prob_script_fname}, runtime: {runtime:.6f}ms (timed on a clean run with no profiler attached; the profiled run below has inflated wall time and is only valid for hotspot attribution)

{profile_output}
</profiler_output>
""")

if __name__ == "__main__":
    main()
