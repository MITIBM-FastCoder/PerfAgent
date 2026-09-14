# PerfAgent

**Profiler-Guided Iterative Refinement for Repository-Level Code Optimization**

Ryan Deng (MIT), Yuanzhe Liu (RPI), Bastian Lipka (IBM), Yao Ma (RPI), Xuhao Chen (Michigan State), Tim Kaler (MIT)&dagger;, Jatin Ganhotra (IBM Research)&dagger;

&dagger; co-senior authors

[arXiv:2607.19653](https://arxiv.org/abs/2607.19653) (cs.SE)

This repository contains the harness used to run PerfAgent on the [GSO](https://gso-bench.github.io/) and [SWE-fficiency](https://swefficiency.com/) benchmarks.

<p align="center">
  <img src="docs/overview.png" alt="PerfAgent overview" width="720">
</p>

<p align="center"><sub>Figure 1 from the paper: PerfAgent wraps a coding agent with a profiler, a loop controller, and selective test validation.</sub></p>

> **On two challenging optimization benchmarks, GSO and SWE-fficiency-Lite, PerfAgent more than doubles the rate of expert-matching patches over OpenHands with GPT-5.1, improving from 19.6% to 41.2% on GSO and from 26% to 74% on SWE-fficiency-Lite.**

## Table of contents

- [PerfAgent](#perfagent)
  - [Table of contents](#table-of-contents)
  - [How it works](#how-it-works)
    - [Pipeline](#pipeline)
  - [Benchmarks](#benchmarks)
  - [Results](#results)
    - [GSO](#gso)
    - [SWE-fficiency-Lite](#swe-fficiency-lite)
  - [Prerequisites](#prerequisites)
  - [Install](#install)
  - [Quickstart](#quickstart)
  - [CLI reference](#cli-reference)
  - [Configuration](#configuration)
    - [Cost and step limits](#cost-and-step-limits)
    - [The str\_replace\_editor tool](#the-str_replace_editor-tool)
  - [Test DB (required)](#test-db-required)
  - [Docker images](#docker-images)
    - [Patched py-spy](#patched-py-spy)
    - [Profiling loop](#profiling-loop)
  - [Code layout](#code-layout)
  - [artifacts/](#artifacts)
  - [Reproducing the paper](#reproducing-the-paper)
  - [FAQ / troubleshooting](#faq--troubleshooting)
  - [Citation](#citation)

## How it works

PerfAgent wraps an off-the-shelf coding agent ([Mini-SWE-Agent](https://github.com/SWE-agent/mini-swe-agent)) with three feedback mechanisms. Each one targets a specific failure mode of LLM agents running on these benchmarks.

1. **Curated profiler usage**, addresses agents missing the real bottleneck.
   The agent gets a profile of the program from the [py-spy](https://github.com/benfred/py-spy) profiler. It captures both Python and native-extension frames and produces raw stack frames. These raw stack frames are parsed using `parse_pyspy.py`, and a json output is produced. The json contains hotspots with info on location, call stack, self-time, total-time. PerfAgent then queries a LLM to summarize the output for the coding agent.

2. **Objective-driven loop controller**, addresses agents terminating prematurely.
   When the agent signals STOP (in mini-swe-agent's case the command is `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`), the harness applies the patch, rebuilds the repository, revalidates it, and profiles it again. It then reports the updated hotspots and the measured speedup, and asks the agent to continue, for up to `theta = 5` iterations. At the end, PerfAgent selects the best-performing CORRECT patch across all iterations. Note that best-performing means only on the provided workload. GSO, for example, has hidden performance tests that PerfAgent does not have access to.

3. **Selective validation**, against insufficient testing.
   [pytest-testmon](https://github.com/tarpas/pytest-testmon) runs only the tests whose coverage overlaps the agent's changes. A failing test is returned to the agent as feedback.

### Pipeline

1. Input: a repository checked out at a commit, plus a workload script.
2. Baseline profile: run the workload once, profile it, summarize the hotspots.
3. Agent turn: the agent reads the profile and edits the repository.
4. Intercept STOP: when the agent tries to end the run, the harness catches it instead of exiting.
5. Rebuild and selectively validate: rebuild the repo, run only the tests that cover the diff. A failure returns to the agent as feedback and the loop continues.
6. Measure and re-profile: time the workload (first run only) and take a fresh profile.
7. Best-patch selector: record this attempt if it is a correct, faster patch than the current best.
8. Loop while iterations `< theta` (default 5), back to step 3.
9. Output: the fastest correct patch found across all iterations.

<p align="center">
  <img src="docs/pipeline.png" alt="PerfAgent pipeline" width="720">
</p>

<p align="center"><sub>Overview of agentic loop, from the paper.</sub></p>

## Benchmarks

| Benchmark | Repos | Tasks | Median expert speedup | Median expert patch size (LOC) | Language mix (Python / C+C++ / Cython / Rust) |
|---|---|---|---|---|---|
| [GSO](https://github.com/gso-bench/gso) | 10 | 102 | 2.43x | 140 | 41% / 45% / 10% / 4% |
| [SWE-fficiency-Lite](https://github.com/swefficiency/swefficiency) | 9 | 100 | 3.57x | 20 | 88% / 1% / 11% / 0% |

GSO has hidden performance tests beyond the workload script which the agent does not have access to. SWE-fficiency-Lite is a 100-task random subset of SWE-fficiency with no hidden tests.

**Metrics**

- **SR** (speedup ratio) = agent speedup / human-expert speedup.
- **Opt@1** = percent of tasks that are correct AND have SR &ge; 0.95.
- **Sp@1** = percent of tasks with at least 1.2x speedup over the base repository.
- **Correctness** = percent of tasks passing the benchmark's correctness tests.
- **Hack-Adj.** = Opt@1 recomputed after removing patches flagged by the combined reward-hacking detector.

## Results

All numbers below are for GPT-5.1. Columns are Correctness / Sp@1 / Opt@1 / Hack-Adj., all in percent.

### GSO

| Method | Correctness | Sp@1 | Opt@1 | Hack-Adj. |
|---|---|---|---|---|
| OpenHands | 88.2 | 46.1 | 20.6 | 19.6 |
| Codex | 89.2 | 48.0 | 18.6 | 17.7 |
| **PerfAgent** | **93.1** | **74.5** | **42.1** | **41.2** |

### SWE-fficiency-Lite

| Method | Correctness | Sp@1 | Opt@1 | Hack-Adj. |
|---|---|---|---|---|
| OpenHands | 82 | 47 | 27 | 26 |
| Codex | 80 | 59 | 39 | 39 |
| **PerfAgent** | **98** | **80** | **74** | **74** |

## Prerequisites

- Python 3.12 or newer.
- [`uv`](https://docs.astral.sh/uv/).
- Docker. All tasks are run within a docker container.
- Docker images pulled per instance from Docker Hub (`ryandeng1/perfagent:{benchmark}.{instance_id}`). Each task has its own image, built for that repository at that commit. Image sizes are not measured or recorded anywhere in this repository, so budget disk space conservatively before a full run. `py-spy` itself runs *inside* the container, as part of the image. Do not install `py-spy` on the host.
- The `test_db` artifact, downloaded from the Hugging Face dataset [`ryandeng/perfagent-test-db`](https://huggingface.co/datasets/ryandeng/perfagent-test-db). See [Test DB](#test-db-required) for the download command and where to point the harness.
- A Hugging Face token `HF_TOKEN`, and an LLM provider key such as `OPENAI_API_KEY`.

## Install

```bash
git clone https://github.com/MITIBM-FastCoder/PerfAgent.git
cd PerfAgent
uv sync
```

## Quickstart

```bash
export HF_TOKEN=...          # for some GSO tasks that may require downloading data from huggingface
export OPENAI_API_KEY=...    # or alternatively some other LLM provider API key

uv run perfagent \
  --config-path configs/gso.yaml \
  --test-db-root test_db/gso \
  --instance-id numpy__numpy-09db9c7 \
  --output-path outputs/ \
  --traj-path trajs/
```

Outputs, per instance:

- `outputs/<instance_id>/opt_attempts.json`: a list of `{runtime, speedup, perf_report, diff}`, one entry per optimization attempt the agent made.
- `trajs/<instance_id>/traj.json`: the full agent trajectory.

## CLI reference

| Flag | Required | Meaning |
|---|---|---|
| `--config-path PATH` | yes | Path to a run-config YAML (see [Configuration](#configuration)). |
| `--instance-id STR` | one of these two | Instance to run, by instance id. Mutually exclusive with `--run-id`. |
| `--run-id INT` | one of these two | Instance to run, by row index in the huggingface dataset (useful for slurm array jobs). Mutually exclusive with `--instance-id`. |
| `--output-path PATH` | yes | Directory to write `<instance_id>/opt_attempts.json` into. |
| `--traj-path PATH` | yes | Directory to write `<instance_id>/traj.json` into. |
| `--test-db-root PATH` | yes | Benchmark subdirectory of the downloaded `test_db` artifact, e.g. `test_db/gso`. |

## Configuration

A run config is a YAML file with four possible top-level keys: `benchmark`, `agent`, `environment`, `model`. Example configs are in `configs/gso.yaml` and `configs/swefficiency.yaml` used for the paper's GPT 5.1 results.

| Key | Required | Meaning |
|---|---|---|
| `benchmark.name` | yes | Benchmark adapter: `gso` or `swefficiency`. |
| `benchmark.dataset` | yes | Hugging Face dataset id: `gso-bench/gso` or `swefficiency/swefficiency_lite`. |
| `agent.*` | no | Maps to `PerfAgentConfig` / mini-swe-agent's `AgentConfig`. Contains standard templates used when running the agent, along with options to configure the cost/step limit for each run. |
| `model.extra_tools` | no | Additional tools besides `bash` the model can use. Right now only `[str_replace_editor]` is supported, which was used when running PerfAgent on Kimi-K2. See [The str_replace_editor tool](#the-str_replace_editor-tool). |

For example, the benchmark block in `configs/gso.yaml` is:

```yaml
benchmark:
  name: gso
  dataset: gso-bench/gso
```

### Cost and step limits

The configs set `agent.cost_limit: 5.0` (USD per task) and `agent.step_limit: 200`.

### The str_replace_editor tool

By default the model has one tool, `bash`, which is how mini-swe-agent works. The paper's Kimi-K2 runs added the OpenHands-style `str_replace_editor` tool (`view`, `create`, `str_replace`, `insert`, `undo_edit`), because we found that Kimi-K2 struggled with editing files through baseh. Enable it by adding this to the config:

```yaml
model:
  extra_tools: [str_replace_editor]
```

## Test DB (required)

`test_db` holds, per instance, the calibrated stable test suite the harness runs to validate a patch. It is published as the Hugging Face dataset [`ryandeng/perfagent-test-db`](https://huggingface.co/datasets/ryandeng/perfagent-test-db). The dataset card describes how the suites were calibrated.

| Benchmark | Download size |
|---|---|
| GSO | 29 MB |
| SWE-fficiency-Lite | 14.5 GB, almost all of it the per-instance `.testmondata` seeds |

Download it with the `hf` CLI, which `uv sync` installs into the project environment:

```bash
uv run hf download ryandeng/perfagent-test-db --repo-type dataset --local-dir test_db
```

This creates `test_db/gso/<instance_id>/...` and `test_db/swefficiency/<instance_id>/...`. Point the harness at the **benchmark subdirectory** with the required CLI flag: `--test-db-root test_db/gso` or `--test-db-root test_db/swefficiency`.

The test_db contains information on the set of tests to include/exclude when validating the agent's patch, and is copied to the docker container at runtime. Tests are excluded if they are flaky or run for a unusually long time. This list may not be comprehensive and flaky tests may still remain, which is something to look out for when running PerfAgent. Right now, all tests are run with a single worker to minimize the occurrence of flaky tests.

## Docker images

Images are pulled from Docker Hub at `ryandeng1/perfagent:{benchmark}.{instance_id}`, where `benchmark` is `gso` or `swefficiency` and `instance_id` is the specific task id. Each benchmark task has its own image (102 for GSO, 100 for SWE-fficiency-Lite).

### Patched py-spy
Right now the docker images built py-spy 0.4.1 by default. There is ongoing work fixing some of the issues with py-spy on GSO and SWE-fficiency and integrating it within the docker images.

For now, set `environment.pyspy: image` in the run config to use the image's py-spy which works fine for most benchmark tasks.

### Profiling loop

`src/perfagent/assets/{gso,swefficiency}/workloads/`  contains the scripts used to evaluate the agent's patch. Every `perf_script.py` uses roughly the same `timeit.template`. It times one call of `experiment()` on the data `setup()` produced, and then keeps calling `experiment()` on that same data for 10 seconds by default so that py-spy has enough samples.

For some instances, the `experiment()` function is not idempotent, so `setup()` has to be called every time in the timing loop as well. For some of these instances, the time it takes to run `setup()` far exceeds the time it takes to run the workload, and profiling for 10 seconds doesn't produce enough samples. Therefore, for those instances, we profile for a little bit longer (currently set to 30 seconds).

From the script, it's important to note that the reported timing is the *first* run only, not an average over the profiling loop's repeated executions. This is meant to discourage the agent from caching results across timing iterations, which would lower the average runtime. In one ablation, this change dropped flagged reward hacks from 18 to 3.


## Code layout

- `src/perfagent/adapters/`: benchmark-specific code that builds the `HarnessSpec` for each instance. The benchmark-specific adapters produce the build script, test script etc. for the tasks in a particular benchmark. A lot of the code which is taken from the [`GSO`](https://github.com/gso-bench/gso) and [`SWE-fficiency`](https://github.com/swefficiency/swefficiency) repositories.
- `src/perfagent/workspace.py`: pulls the Docker image and starts the container (installs the relevant packages, copies build/test/profiler/workload scripts, extracts the stable test suite, seeds testmon data).
- `src/perfagent/pyspy.py` and `src/perfagent/assets/pyspy/`: the py-spy patch and the script that builds and installs it inside each task container. See [Patched py-spy](#patched-py-spy). Currently, this is still a work in progress.
- `src/perfagent/environment.py` (`PerfDockerEnvironment`): mini-swe-agent's Docker environment with some added options to make it work with GSO and SWE-fficiency.
- `src/perfagent/agent.py` (`PerfAgent`): the agent loop, built on [`mini-swe-agent`](https://github.com/SWE-agent/mini-swe-agent).
- `src/perfagent/tools/` and `src/perfagent/assets/tools/`: extra tools the model can call besides bash. Right now `str_replace_editor` is the only tool supported. See [The str_replace_editor tool](#the-str_replace_editor-tool).
- `src/perfagent/model.py` (`PerfLitellmModel`): thin litellm wrapper to allow for raw LLM queries (without tool calls) used to summarize profiler output.

## artifacts/

- `artifacts/predictions/gso.jsonl`, `artifacts/predictions/swefficiency.jsonl`: the model's patches for every task for GPT 5.1.
- `artifacts/reports/gso_report.json`, `artifacts/reports/swefficiency.csv`: per-task correctness and speedup results obtained by running the benchmark eval.
- `artifacts/reports/gso_hack_detection.json`, `artifacts/reports/swefficiency_hack_detection.json`: per-task output of the reward-hacking detector. The hack-detector combines the methods of GSO and SWE-fficiency.

## Reproducing the paper

The paper evaluates two models: GPT-5.1 at high reasoning effort, and Kimi-K2 as the open-source model (K2-0711 on GSO, K2-0905 on SWE-fficiency-Lite). For Kimi-K2, the paper adds an structured file-editing tool (`str_replace_editor`) taken from OpenHands, because the open-source models we tested on struggled to edit files reliably through raw bash.

Controller settings: `theta = 5` loop iterations, `$5` max cost per task, `200` step limit.

Hardware: agents ran on an AWS EC2 `c6i.8xlarge` (32 CPU, 64 GB RAM). Benchmark evaluation was run on an `m8i.16xlarge` (64 CPU, 256 GB RAM), matching GSO's and SWE-fficiency's own evaluation setups. Timing results are hardware-sensitive and there can be some small variance between different evaluation runs.

## FAQ / troubleshooting

**How do I use a different LLM as the agent?**
Edit `model.model_name` in your config YAML to any [litellm-supported model id](https://docs.litellm.ai/docs/providers), and set that provider's API key environment variable.

**How much does a run cost, and how do I cap it?**
Set `agent.cost_limit` (USD), `agent.step_limit`, and `agent.max_attempts` in your config. The default configs use `cost_limit: 5.0`, `step_limit: 200`, `max_attempts: 5`. If the agent runs out of cost before running the full 5 attempts, the previous attempts will be stored.

**I get a Docker permission or capability error mentioning `SYS_PTRACE`, `LINUX_IMMUTABLE`, or `seccomp`.**
Task containers require `--cap-add=SYS_PTRACE --cap-add=LINUX_IMMUTABLE --security-opt=seccomp=unconfined`. This may require a root docker installation.

## Citation

If you find this work useful, please cite the PerfAgent paper:

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

This harness builds on [`mini-swe-agent`](https://github.com/SWE-agent/mini-swe-agent) and evaluates on [GSO](https://gso-bench.github.io/) and [SWE-fficiency](https://swefficiency.com/).
