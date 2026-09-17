"""Generates the /run_tests.sh script for GSO/SWE-fficiency used by the agent"""

import shlex
import tarfile
from pathlib import Path, PurePosixPath

from perfagent import repo_config as rc

def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)

def split_pytest_base_args(args: list[str]) -> tuple[list[str], list[str]]:
    structural_args = []
    filter_args = []
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg in {"-m", "--ignore", "--deselect"}:
            if idx + 1 >= len(args):
                raise ValueError(f"missing value for pytest option: {arg}")
            filter_args.extend(args[idx : idx + 2])
            idx += 2
            continue
        if arg.startswith("--ignore=") or arg.startswith("--deselect="):
            filter_args.append(arg)
            idx += 1
            continue
        structural_args.append(arg)
        idx += 1
    return structural_args, filter_args


# --- container-path normalization (gso only) ---


def get_container_config_root(base_dir: str) -> PurePosixPath:
    root = PurePosixPath(base_dir)
    # Some repos run pytest from `/` with `--pyargs`, but config paths still
    # refer to files underneath the checkout at `/testbed`.
    if root == PurePosixPath("/"):
        return PurePosixPath("/testbed")
    return root


def normalize_container_path(path: str, *, base_dir: str = "/testbed") -> str:
    posix_path = PurePosixPath(path)
    if posix_path.is_absolute():
        return str(posix_path)
    config_root = get_container_config_root(base_dir)
    base_root = config_root.as_posix().lstrip("/")
    normalized = posix_path.as_posix().lstrip("./")
    if normalized == base_root or normalized.startswith(f"{base_root}/"):
        return str(PurePosixPath("/") / normalized)
    return str(config_root / posix_path)


def normalize_container_nodeid(nodeid: str, *, base_dir: str = "/testbed") -> str:
    path_part, sep, remainder = nodeid.partition("::")
    posix_path = PurePosixPath(path_part)
    config_root = get_container_config_root(base_dir)
    base_root = config_root.as_posix().lstrip("/")

    if posix_path.is_absolute():
        normalized_path = posix_path.as_posix().lstrip("/")
    else:
        normalized = posix_path.as_posix().lstrip("./")
        if normalized == base_root or normalized.startswith(f"{base_root}/"):
            normalized_path = normalized
        else:
            normalized_path = str(PurePosixPath(base_root) / posix_path).lstrip("/")

    if not sep:
        return normalized_path
    return f"{normalized_path}{sep}{remainder}"


def normalize_excluded_collector_path(path: str, *, pytest_cwd: str) -> str:
    normalized = path.strip()
    if not normalized:
        return normalized
    if normalized.startswith("/"):
        return normalized
    if normalized == "testbed" or normalized.startswith("testbed/"):
        return f"/{normalized.lstrip('/')}"
    return normalize_container_path(normalized, base_dir=pytest_cwd)


# --- stable-suite ignore args (host-side for both benchmarks) ---


def _read_excluded_collectors(stable_suite_tar: Path) -> list[str] | None:
    if not stable_suite_tar.is_file():
        raise FileNotFoundError(f"missing stable suite artifact: {stable_suite_tar}")
    with tarfile.open(stable_suite_tar, "r:gz") as tar:
        try:
            excluded = tar.extractfile("stable_suite/excluded_collectors.txt")
        except KeyError:
            return None
        if excluded is None:
            return None
        return excluded.read().decode("utf-8").splitlines()


def gso_stable_suite_ignore_args(stable_suite_tar: Path, *, pytest_cwd: str) -> list[str]:
    lines = _read_excluded_collectors(stable_suite_tar)
    ignore_args: list[str] = []
    for raw_line in lines or []:
        normalized = normalize_excluded_collector_path(raw_line, pytest_cwd=pytest_cwd)
        if normalized:
            ignore_args.append(f"--ignore={normalized}")
    return ignore_args


def sweff_stable_suite_ignore_args(stable_suite_tar: Path) -> list[str]:
    # Mirrors the old in-container `sed '/^$/d; s/^/--ignore=/'`: only
    # exactly-empty lines are dropped, no other normalization.
    lines = _read_excluded_collectors(stable_suite_tar)
    return [f"--ignore={line}" for line in lines or [] if line]


# --- gso assembly ---


def gso_pytest_cwd(config: dict, repo: str) -> str:
    return rc.repo_cfg(config, repo).get("pytest_cwd", "/testbed")


def gso_pytest_command(config: dict, repo: str) -> list[str]:
    return rc.repo_cfg(config, repo).get("pytest_command", ["pytest"])


def gso_testmon_data_path(config: dict, repo: str) -> str:
    return str(PurePosixPath(gso_pytest_cwd(config, repo)) / ".testmondata")


def _gso_base_args(config: dict, repo: str, instance_id: str) -> list[str]:
    repo_cfg = rc.repo_cfg(config, repo)
    pytest_cwd = gso_pytest_cwd(config, repo)
    args = shlex.split(repo_cfg["base_args"])
    for nodeid in repo_cfg.get("deselect") or []:
        args.append(f"--deselect={normalize_container_nodeid(nodeid, base_dir=pytest_cwd)}")
    for nodeid in rc.override_map(config, "extra_deselects", instance_id, []):
        args.append(f"--deselect={normalize_container_nodeid(nodeid, base_dir=pytest_cwd)}")
    for path in repo_cfg.get("ignore") or []:
        args.append(f"--ignore={normalize_container_path(path, base_dir=pytest_cwd)}")
    for path in rc.override_map(config, "extra_ignores", instance_id, []):
        args.append(f"--ignore={normalize_container_path(path, base_dir=pytest_cwd)}")
    args.extend(["--timeout", "300"])
    return args


def _gso_targets(config: dict, repo: str, instance_id: str) -> list[str]:
    repo_cfg = rc.repo_cfg(config, repo)
    pytest_cwd = gso_pytest_cwd(config, repo)
    targets = [
        normalize_container_path(path, base_dir=pytest_cwd) for path in repo_cfg.get("targets") or []
    ]
    targets.extend(
        normalize_container_path(path, base_dir=pytest_cwd)
        for path in rc.override_map(config, "targets", instance_id, [])
    )
    return targets

def build_gso_run_tests_script(instance_id: str, repo: str, stable_suite_tar: Path) -> str:
    config = rc.get_repo_config("gso")
    pytest_cwd = gso_pytest_cwd(config, repo)
    structural_args, filter_args = split_pytest_base_args(_gso_base_args(config, repo, instance_id))

    pytest_args = list(structural_args)
    pytest_args.extend(filter_args)
    pytest_args.extend(["-p", "no:randomly"])
    pytest_args.extend(["--testmon", "--testmon-forceselect"])
    pytest_args.extend(["-p", "deselect_plugin"])
    pytest_args.extend(["-p", "test_stats_plugin"])
    pytest_args.extend(_gso_targets(config, repo, instance_id))
    pytest_args.extend(gso_stable_suite_ignore_args(stable_suite_tar, pytest_cwd=pytest_cwd))

    pytest_cmd = shell_join([*gso_pytest_command(config, repo), *pytest_args])
    return "\n".join(
        [
            "#!/bin/bash",
            "set -euxo pipefail",
            f"cd {shlex.quote(pytest_cwd)}",
            'export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"',
            f"EXCLUDED_NODEIDS_FILE=/stable_suite/excluded_nodeids.txt {pytest_cmd}",
        ]
    )


# --- swefficiency assembly ---


def _sweff_arg_parts(config: dict, repo: str, instance_id: str) -> tuple[list[str], list[str]]:
    repo_cfg = rc.repo_cfg(config, repo)
    structural_args, filter_args = split_pytest_base_args(shlex.split(repo_cfg["base_args"]))

    for nodeid in repo_cfg.get("deselect") or []:
        filter_args.append(f"--deselect={nodeid}")
    for nodeid in rc.override_map(config, "extra_deselects", instance_id, []):
        filter_args.append(f"--deselect={nodeid}")
    for path in repo_cfg.get("ignore") or []:
        filter_args.append(f"--ignore={path}")
    for path in rc.override_map(config, "extra_ignores", instance_id, []):
        filter_args.append(f"--ignore={path}")

    structural_args.extend(["--timeout", "300"])
    # Declarative replacements for the old per-repo/per-instance `-p <plugin>`
    # if-ladders. actual_run is never collect-only, so *_run_only always applies.
    structural_args.extend(repo_cfg.get("extra_structural_args") or [])
    structural_args.extend(rc.override_map(config, "extra_structural_args_run_only", instance_id, []))
    structural_args.extend(rc.override_map(config, "extra_structural_args", instance_id, []))
    return structural_args, filter_args

def build_sweff_run_tests_script(instance_id: str, repo: str, stable_suite_tar: Path) -> str:
    config = rc.get_repo_config("swefficiency")
    structural_args, filter_args = _sweff_arg_parts(config, repo, instance_id)

    pytest_args = list(structural_args)
    pytest_args.extend(filter_args)
    pytest_args.extend(["-p", "no:randomly", "--testmon", "--testmon-forceselect"])
    pytest_args.extend(["-p", "deselect_plugin"])
    pytest_args.extend(["-p", "test_stats_plugin"])
    pytest_args.extend(sweff_stable_suite_ignore_args(stable_suite_tar))

    pytest_cmd = shell_join(["pytest", *pytest_args])
    return "\n".join(
        [
            "#!/bin/bash",
            "set -euxo pipefail",
            "cd /testbed",
            "TESTMON_DATAFILE=/.testmondata "
            f"EXCLUDED_NODEIDS_FILE=/stable_suite/excluded_nodeids.txt {pytest_cmd}",
        ]
    )
