"""SWE-fficiency benchmark adapter."""

from functools import cache
from pathlib import Path

import yaml

from perfagent import pytest_cmd
from perfagent import repo_config as rc
from perfagent.adapters.base import IMAGE_REPO, PACKAGED_ASSET_HINT, BenchmarkAdapter, Instance, require_artifact
from perfagent.spec import ContainerFile, HarnessSpec, SetupCommand

PROFILER_VARIANT_FILES = {
    "default": "profile_prob_script.py",
    "no_native": "profile_prob_script_no_native.py",
}

PYTEST_TOOLING_INSTALL = "pip install pytest pytest-testmon pytest-timeout pytest-xdist"

# Obtain the specific build command for each benchmark task in SWE-fficiency, taken from the SWE-fficiency repository (https://github.com/swefficiency/swefficiency).
@cache
def get_install_specs() -> dict:
    path = rc.assets_root("swefficiency") / "install_specs.yaml"
    return yaml.safe_load(path.read_text())

def _install_command(repo: str, version: str) -> str:
    specs = get_install_specs()
    try:
        return specs[repo][str(version)]
    except KeyError:
        raise KeyError(
            f"no vendored install spec for {repo} version {version}; "
            "add it to assets/swefficiency/install_specs.yaml from "
            "swefficiency.harness.constants.MAP_REPO_VERSION_TO_SPECS in the swefficiency package"
        ) from None

def _extra_files(config: dict, repo: str, instance_id: str, assets: Path) -> list[ContainerFile]:
    entries = list(rc.repo_cfg(config, repo).get("extra_files") or [])
    entries += rc.override_map(config, "extra_files", instance_id, [])
    files = []
    for entry in entries:
        src = assets / entry["src"]
        dest = entry["dest"]
        if dest.endswith("/"):
            dest = dest + src.name
        elif dest == "/":
            dest = f"/{src.name}"
        files.append(ContainerFile(src=src, dest=dest))
    return files

def _setup_commands(config: dict, repo: str, instance_id: str) -> list[SetupCommand]:
    def to_cmd(entry: dict) -> SetupCommand:
        return SetupCommand(
            command=entry["command"],
            cwd=entry.get("cwd", "/"),
            context=entry.get("context", ""),
        )

    commands = [to_cmd(e) for e in rc.repo_cfg(config, repo).get("setup_commands") or []]
    commands.append(SetupCommand(command=PYTEST_TOOLING_INSTALL, context="install pytest tooling"))
    commands += [
        SetupCommand(
            command="command -v rg || (apt-get update && apt-get install -y ripgrep)",
            context="install rg",
        ),
        SetupCommand(
            command="command -v jq || (apt-get update && apt-get install -y jq)",
            context="install jq",
        ),
    ]
    commands += [to_cmd(e) for e in rc.override_map(config, "setup_commands", instance_id, [])]
    return commands

class SwefficiencyAdapter(BenchmarkAdapter):
    name = "swefficiency"

    def build_spec(self, instance: Instance, *, test_db_root: Path) -> HarnessSpec:
        instance_id, repo = instance.instance_id, instance.repo
        config = rc.get_repo_config("swefficiency")
        assets = rc.assets_root("swefficiency")

        stable_suite_tar = require_artifact(
            test_db_root / instance_id / "stable_suite.tar.gz",
            instance_id=instance_id,
            what="stable suite artifact",
        )
        testmon_seed = require_artifact(
            test_db_root / instance_id / ".testmondata",
            instance_id=instance_id,
            what="testmon seed database",
        )
        workload = require_artifact(
            assets / "workloads" / instance_id / "perf_script.py",
            instance_id=instance_id,
            what="workload script (packaged asset)",
            hint=PACKAGED_ASSET_HINT,
        )

        build_script = "\n".join(
            ["#!/bin/bash", "set -euxo pipefail"]
            # add debug symbols for profiler
            + ['export CFLAGS="-O2 -g"', 'export CXXFLAGS="-O2 -g"']
            + ["cd /testbed"]
            + [_install_command(repo, instance.raw["version"])]
        )

        test_script = pytest_cmd.build_sweff_run_tests_script(instance_id, repo, stable_suite_tar)

        repo_cfg = rc.repo_cfg(config, repo)
        profiler_variant = rc.override_map(
            config, "profiler_variant", instance_id, repo_cfg.get("profiler_variant", "default")
        )

        files = _extra_files(config, repo, instance_id, assets)
        files += [
            ContainerFile(src=assets / "scripts" / "deselect_plugin.py", dest="/deselect_plugin.py"),
            ContainerFile(src=assets / "scripts" / "test_stats_plugin.py", dest="/test_stats_plugin.py"),
            ContainerFile(src=workload, dest="/perf_script.py", immutable=True),
            ContainerFile(
                src=assets / "profiler" / PROFILER_VARIANT_FILES[profiler_variant],
                dest="/profile_prob_script.py",
                immutable=True,
            ),
            # The profiler scripts invoke the parser as parse_pyspy_compat.py;
            # the enhanced parser ships under that name.
            ContainerFile(
                src=assets / "profiler" / "parse_pyspy_enhanced.py",
                dest="/parse_pyspy_compat.py",
                immutable=True,
            ),
        ]

        env = {"PYTHONPATH": "/", "PYTHONHASHSEED": "0"}
        env |= rc.override_map(config, "env", instance_id, {})

        return HarnessSpec(
            instance_id=instance_id,
            repo=repo,
            image=f"{IMAGE_REPO}:{self.image_tag(instance)}",
            build_script=build_script,
            test_script=test_script,
            files=files,
            stable_suite_tar=stable_suite_tar,
            testmon_seed=testmon_seed,
            setup_commands=_setup_commands(config, repo, instance_id),
            env=env,
            agent_run_kwargs={"perf_script": workload.read_text()},
        )
