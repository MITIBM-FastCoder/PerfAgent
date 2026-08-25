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

class BenchmarkAdapter:
    name: str

    def load_instance(self, dataset_name: str, split: str, *, instance_id: str | None, run_id: int | None) -> Instance:
        row = load_dataset_row(dataset_name, split, instance_id=instance_id, run_id=run_id)
        return Instance(instance_id=row["instance_id"], repo=row["repo"], raw=row)

    def image_tag(self, instance: Instance) -> str:
        return f"{self.name}.{instance.instance_id}"

    def build_spec(self, instance: Instance, *, test_db_root: Path) -> HarnessSpec:
        raise NotImplementedError


def load_dataset_row(dataset_name: str, split: str, *, instance_id: str | None, run_id: int | None) -> dict:
    if (instance_id is None) == (run_id is None):
        raise ValueError("exactly one of instance_id / run_id must be given")
    dataset = load_dataset(dataset_name, split=split)
    if instance_id is not None:
        filtered = dataset.filter(lambda example: example["instance_id"] == instance_id)
        if len(filtered) != 1:
            raise ValueError(f"could not find instance id {instance_id!r} in {dataset_name}")
        return filtered[0]
    if not 0 <= run_id < len(dataset):
        raise ValueError(f"run id {run_id} out of range for {dataset_name} ({len(dataset)} rows)")
    return dataset[run_id]

def require_artifact(path: Path, *, instance_id: str, what: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(
            f"missing {what} for {instance_id}: {path}\n"
            "Check benchmark.test_db_root in your run config (or --test-db-root); "
            "artifacts are regenerable with the old repo's get_test_db.py."
        )
    return path
