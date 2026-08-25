from functools import cache
from importlib import resources
from pathlib import Path

import yaml

def assets_root(benchmark: str) -> Path:
    root = resources.files("perfagent") / "assets" / benchmark
    return Path(str(root))


@cache
def get_repo_config(benchmark: str) -> dict:
    config_path = assets_root(benchmark) / "repo_config.yaml"
    return yaml.safe_load(config_path.read_text())


def repo_cfg(config: dict, repo: str) -> dict:
    cfg = config["repos"].get(repo)
    if cfg is None:
        raise ValueError(f"no repo config for: {repo}")
    return cfg


def instance_overrides(config: dict) -> dict:
    return config.get("instance_overrides", {})


def override_list(config: dict, key: str) -> set[str]:
    """Membership lists like patch_pandas_skip_slow / patch_pydantic_yield_fixture."""
    return set(instance_overrides(config).get(key) or [])


def override_map(config: dict, key: str, instance_id: str, default=None):
    """Per-instance maps like extra_ignores / profiler_variant."""
    value = (instance_overrides(config).get(key) or {}).get(instance_id)
    return default if value is None else value
