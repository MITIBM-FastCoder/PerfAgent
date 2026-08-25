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
from perfagent.agent import PerfAgent

console = Console(highlight=False)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the perf-optimization agent on a benchmark instance",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--benchmark", choices=["gso", "swefficiency"], required=True)
    parser.add_argument("--config-path", type=Path, required=True, help="run-config yaml")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--run-id", type=int, help="dataset row index (slurm array id)")
    selector.add_argument("--instance-id", type=str, help="instance id")
    parser.add_argument("--output-path", type=Path, required=True, help="output dir (opt_attempts.json)")
    parser.add_argument("--traj-path", type=Path, required=True, help="trajectory dir (traj.json)")
    parser.add_argument("--test-db-root", type=Path, default=None, help="override benchmark.test_db_root")
    return parser.parse_args(argv)


def load_run_config(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text()) or {}
    unknown = set(raw) - {"benchmark", "agent", "environment", "model"}
    if unknown:
        raise ValueError(f"unknown top-level config keys in {path}: {sorted(unknown)}")
    if "benchmark" not in raw:
        raise ValueError(f"config {path} is missing the required 'benchmark' block")
    return raw


def main(argv=None):
    args = parse_args(argv)

    if not os.environ.get("HF_TOKEN"):
        sys.exit(
            "HF_TOKEN is not set. Some benchmark workloads download assets from "
            "Hugging Face inside the container; export HF_TOKEN before running."
        )

    run_config = load_run_config(args.config_path)
    benchmark_config = run_config["benchmark"]
    adapter = get_adapter(args.benchmark)

    instance = adapter.load_instance(
        benchmark_config["dataset"],
        benchmark_config.get("split", "test"),
        instance_id=args.instance_id,
        run_id=args.run_id,
    )
    console.print(f"[bold green]running {args.benchmark} instance: {instance.instance_id}[/bold green]")
    console.print(f"resolved repo: {instance.repo}")
    console.print(f"Loading run config from [bold green]'{args.config_path}'[/bold green]")

    test_db_root = args.test_db_root or Path(benchmark_config["test_db_root"]).expanduser()
    spec = adapter.build_spec(instance, test_db_root=test_db_root)

    start = time.time()
    env = workspace.materialize(spec, run_config.get("environment") or {})

    instance_id = instance.instance_id
    traj_file = args.traj_path / instance_id / "traj.json"

    contract_fields = {
        "build_command": spec.build_script_path,
        "test_command": spec.test_script_path,
        "profile_command": spec.profile_command,
        "reference_profile_command": spec.reference_profile_command,
        "workload_script": spec.workload_script_path,
        "output_path": traj_file,
    }
    agent = PerfAgent(
        model=get_model(config=run_config.get("model") or {}),
        env=env,
        **{**contract_fields, **(run_config.get("agent") or {})},
    )

    result = agent.run(instance_id, **spec.agent_run_kwargs)

    (args.output_path / instance_id).mkdir(parents=True, exist_ok=True)
    with open(args.output_path / instance_id / "opt_attempts.json", "w") as f:
        json.dump(result["opt_attempts"], f)
    agent.save(traj_file)

    console.print(
        f"ran {args.benchmark} on instance: {instance_id}, took: {time.time() - start} seconds.",
        style="bright_magenta",
    )


if __name__ == "__main__":
    main()
