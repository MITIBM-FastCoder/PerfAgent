from dataclasses import dataclass
from pathlib import Path

from datasets import load_dataset

from perfagent.spec import HarnessSpec

# DockerHub repo holding the docker images, tag for each task is "<benchmark>.<instance_id>".
IMAGE_REPO = "ryandeng1/perfagent"

@dataclass
class Instance:
    instance_id: str
    repo: str
    raw: dict  # the plain HF dataset row

DATASET_SPLIT = "test"
"""Both benchmark datasets (gso-bench/gso, swefficiency/swefficiency_lite) publish only this split."""


class BenchmarkAdapter:
    name: str

    def load_instance(self, dataset_name: str, *, instance_id: str | None, run_id: int | None) -> Instance:
        row = load_dataset_row(dataset_name, instance_id=instance_id, run_id=run_id)
        return Instance(instance_id=row["instance_id"], repo=row["repo"], raw=row)

    def image_tag(self, instance: Instance) -> str:
        return f"{self.name}.{instance.instance_id}"

    def build_spec(self, instance: Instance, *, test_db_root: Path) -> HarnessSpec:
        raise NotImplementedError


def load_dataset_row(dataset_name: str, *, instance_id: str | None, run_id: int | None) -> dict:
    if (instance_id is None) == (run_id is None):
        raise ValueError("exactly one of instance_id / run_id must be given")
    dataset = load_dataset(dataset_name, split=DATASET_SPLIT)
    if instance_id is not None:
        filtered = dataset.filter(lambda example: example["instance_id"] == instance_id)
        if len(filtered) != 1:
            raise ValueError(f"could not find instance id {instance_id!r} in {dataset_name}")
        return filtered[0]
    if not 0 <= run_id < len(dataset):
        raise ValueError(f"run id {run_id} out of range for {dataset_name} ({len(dataset)} rows)")
    return dataset[run_id]

TEST_DB_HINT = (
    "Download the test_db dataset (https://huggingface.co/datasets/ryandeng/perfagent-test-db) "
    "and point --test-db-root at its gso/ or "
    "swefficiency/ subdirectory. See README, section 'Test DB'."
)
PACKAGED_ASSET_HINT = (
    "This file ships inside the perfagent package (src/perfagent/assets/). "
    "Reinstall the package, or check that the instance id is one of the supported tasks."
)

def require_artifact(path: Path, *, instance_id: str, what: str, hint: str = TEST_DB_HINT) -> Path:
    """Return `path` if it is a file, else raise FileNotFoundError naming the artifact and how to get it."""
    if not path.is_file():
        raise FileNotFoundError(f"missing {what} for {instance_id}: {path}\n{hint}")
    return path
