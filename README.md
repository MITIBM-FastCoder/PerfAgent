# PerfAgent: Profiler-Guided Iterative Refinement for Repository-Level Code Optimization

Harness used for the PerfAgent paper.

## Usage

```bash
export HF_TOKEN=...   # required; forwarded into the container, used for some GSO tasks

uv run perfagent --benchmark gso --config-path configs/gso.yaml \
    --instance-id {instance_id} \
    --output-path outputs/ --traj-path trajs/
```

Outputs per instance:
  * `opt_attempts.json`, a list of `{runtime, speedup, perf_report, diff}`, describing the agent's attempts on the task
  * `traj.json`, the trajectory of the agent

## Docker Images 
The docker images are pulled from `ryandeng1/perfagent:{benchmark}.{instance_id}` where benchmark is either `gso` or `swefficiency`, and `instance_id` is the specific instance ID for the benchmark task.

## Data
Each task also needs specific data copied to the docker container before executing the agent.

* Timing script: A modified timing script to allow the profiler to obtain enough samples to accurately profile the benchmark workload, located in `assets/{benchmark}/workloads/{instance_id}/perf_script.py`. To prevent reward hacking, the script only outputs the runtime of the first run.
* Pytest configs:
  * `assets/{benchmark}/repo_config.yaml` contains the specific pytest commands. Some long-running and flaky tests are excluded.
  * `assets/{benchmark}/scripts` contains several pytest plugins and patch scripts to fix pytest errors for some benchmark tasks.
* Profiler scripts: Python scripts that help with profiling.
  * `parse_pyspy.py` parses the raw stackframe output that `py-spy` produces
  * `profile_prob_script.py` is a wrapper around `perf_script.py`, that runs the timing script and the `py-spy` profiler.
* Test-suite artifacts need to be separately downloaded and contain the set of stable tests for each benchmark tasks. The set of stable tests was obtained by removing failing and flaky tests. Once downloaded, point to the location of the test_db inside your config file under `benchmark/test_db_root`.

## Code Overview

- **adapters** (`perfagent/adapters/`) contains benchmark-specific code which sets up the build/test scripts for each benchmark instance.
- **workspace** (`workspace.py`) pulls the docker image, copies relevant files to the docker container (build scripts, test scripts, timing scripts).
- **agent** (`agent.py`, `PerfAgent`), based off of [`mini-swe-agent`](https://github.com/SWE-agent/mini-swe-agent), runs the agent as described in the paper.

## Attribution

If you found this work helpful, please consider citing the SWE-agent paper in your work:

```bibtex
@misc{deng2026perfagent,
      title={PerfAgent: Profiler-Guided Iterative Refinement for Repository-Level Code Optimization}, 
      author={Ryan Deng and Yuanzhe Liu and Bastian Lipka and Yao Ma and Xuhao Chen and Tim Kaler and Jatin Ganhotra},
      year={2026},
      eprint={2607.19653},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2607.19653}, 
}
```