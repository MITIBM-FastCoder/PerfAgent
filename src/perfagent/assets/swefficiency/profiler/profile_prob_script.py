import os
import subprocess
import sys
import tempfile
from pathlib import Path

from typing import Tuple

def time_workload(workload_script: str) -> Tuple[str, bool, float]:
    """Measure the workload runtime from a clean run with no profiler attached.

    py-spy sampling (especially --native) inflates and distorts wall time, so
    the runtime reported to the agent must never come from the instrumented run.
    """
    result = subprocess.run(["python", workload_script], cwd="/", stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
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
    # Parse files from this invocation even if another run has produced /profile.folded.
    with tempfile.TemporaryDirectory(dir="/") as tmp:
        folded = Path(tmp) / "profile.folded"
        workers = Path(tmp) / "workers.folded"
        cmd = ["py-spy", "record", "--native", "-r", "50", "-f", "raw", "-o", str(folded),
               "--", "python", workload_script]
        result = subprocess.run(
            cmd, cwd="/", stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            env=dict(os.environ, PERFAGENT_SIBLING_PROFILE=str(workers)),
        )
        if os.environ.get("PYSPY_LOG_FILE"):
            Path(os.environ["PYSPY_LOG_FILE"]).write_text(result.stdout + result.stderr)
        # Older recorders can report ECHILD after successfully writing the profile.
        if (result.returncode and "No child processes" not in result.stdout + result.stderr
                or not folded.is_file() or not any(line.startswith("Mean:") for line in result.stdout.splitlines())):
            return f"error profiling workload:\n{result.stdout}\n{result.stderr}", False

        parse_cmd = ["python", "/parse_pyspy_compat.py", str(folded)]
        if workers.is_file():  # Stock image binaries do not produce the optional worker profile.
            parse_cmd.extend(["--workers", str(workers)])
        parsed = subprocess.run(parse_cmd, cwd="/", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True)
        if parsed.returncode:
            return f"error parsing profile:\n{parsed.stderr}", False
        folded.replace("/profile.folded")
        return parsed.stdout.strip(), True

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
