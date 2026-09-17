import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml
from rich.console import Console

from minisweagent.models import get_model

from perfagent import workspace
from perfagent.adapters import get_adapter
from perfagent.agent import PerfAgent, PerfAgentConfig

console = Console(highlight=False)

HARNESS_AGENT_FIELDS = {
    "build_command",
    "test_command",
    "profile_command",
    "reference_profile_command",
    "workload_script",
    "output_path",
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the perf-optimization agent on a benchmark instance",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config-path", type=Path, required=True, help="run-config yaml")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--run-id", type=int, help="dataset row index (slurm array id)")
    selector.add_argument("--instance-id", type=str, help="instance id")
    parser.add_argument("--output-path", type=Path, required=True, help="output dir (opt_attempts.json)")
    parser.add_argument("--traj-path", type=Path, required=True, help="trajectory dir (traj.json)")
    parser.add_argument("--test-db-root", type=Path, required=True, help="benchmark test_db directory")
    return parser.parse_args(argv)


def load_run_config(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text())
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"config {path} must be a YAML mapping")
    unknown = set(raw) - {"benchmark", "agent", "environment", "model"}
    if unknown:
        raise ValueError(f"unknown top-level config keys in {path}: {sorted(unknown)}")
    if "benchmark" not in raw:
        raise ValueError(f"config {path} is missing the required 'benchmark' block")
    benchmark_config = raw["benchmark"]
    if not isinstance(benchmark_config, dict):
        raise ValueError(f"benchmark config in {path} must be a mapping")
    unknown = set(benchmark_config) - {"name", "dataset"}
    if unknown:
        hint = " ('split' is gone: both datasets only have a test split)" if "split" in unknown else ""
        if "test_db_root" in unknown:
            hint += " (test_db_root belongs on the CLI: use --test-db-root)"
        raise ValueError(f"unknown benchmark config keys in {path}: {sorted(unknown)}{hint}")
    for key in ("name", "dataset"):
        value = benchmark_config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"config {path} requires a non-empty string for 'benchmark.{key}'")
    if benchmark_config["name"] not in ("gso", "swefficiency"):
        raise ValueError(f"unknown benchmark.name in {path}: {benchmark_config['name']!r}; choose gso or swefficiency")

    for section in ("agent", "environment", "model"):
        if raw.get(section) is not None and not isinstance(raw[section], dict):
            raise ValueError(f"{section} config in {path} must be a mapping")
    agent_config = raw.get("agent") or {}
    reserved = set(agent_config) & HARNESS_AGENT_FIELDS
    if reserved:
        raise ValueError(
            f"agent config keys in {path} are managed by the harness: {sorted(reserved)}; "
            "remove them from the config"
        )
    unknown = set(agent_config) - PerfAgentConfig.model_fields.keys()
    if unknown:
        raise ValueError(f"unknown agent config keys in {path}: {sorted(unknown)}")
    return raw


def main(argv=None):
    args = parse_args(argv)
    run_config = load_run_config(args.config_path)

    if not os.environ.get("HF_TOKEN"):
        sys.exit(
            "HF_TOKEN is not set. Some benchmark workloads download assets from "
            "Hugging Face inside the container; export HF_TOKEN before running."
        )

    benchmark_config = run_config["benchmark"]
    benchmark = benchmark_config["name"]
    adapter = get_adapter(benchmark)

    instance = adapter.load_instance(
        benchmark_config["dataset"],
        instance_id=args.instance_id,
        run_id=args.run_id,
    )
    console.print(f"[bold green]running {benchmark} instance: {instance.instance_id}[/bold green]")
    console.print(f"resolved repo: {instance.repo}")
    console.print(f"Loading run config from [bold green]'{args.config_path}'[/bold green]")

    spec = adapter.build_spec(instance, test_db_root=args.test_db_root.expanduser())

    start = time.time()
    env = workspace.materialize(spec, run_config.get("environment") or {})

    instance_id = instance.instance_id
    traj_file = args.traj_path / instance_id / "traj.json"

    agent = PerfAgent(
        model=get_model(config=run_config.get("model") or {}),
        env=env,
        build_command=spec.build_script_path,
        test_command=spec.test_script_path,
        profile_command=spec.profile_command,
        reference_profile_command=spec.reference_profile_command,
        workload_script=spec.workload_script_path,
        output_path=traj_file,
        **(run_config.get("agent") or {}),
    )

    result = agent.run(instance_id, **spec.agent_run_kwargs)

    (args.output_path / instance_id).mkdir(parents=True, exist_ok=True)
    with open(args.output_path / instance_id / "opt_attempts.json", "w") as f:
        json.dump(result["opt_attempts"], f)
    agent.save(traj_file)

    console.print(
        f"ran {benchmark} on instance: {instance_id}, took: {time.time() - start} seconds.",
        style="bright_magenta",
    )


if __name__ == "__main__":
    main()
