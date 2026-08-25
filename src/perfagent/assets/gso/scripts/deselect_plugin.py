"""Lightweight pytest plugin that deselects tests listed in a file.

The file path is read from the EXCLUDED_NODEIDS_FILE environment variable.
Each line in the file is a pytest node ID to deselect. Blank lines and lines
starting with '#' are ignored.

Usage:
    EXCLUDED_NODEIDS_FILE=/path/to/excluded.txt pytest -p deselect_plugin ...
"""
import os
from pathlib import Path


def _read_excluded_nodeids():
    path = os.environ.get("EXCLUDED_NODEIDS_FILE")
    if not path:
        return set()

    excluded_path = Path(path)
    if not excluded_path.is_file():
        return set()

    nodeids = set()
    with excluded_path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            nodeids.add(line)
    return nodeids

def pytest_configure(config):
    config._deselect_excluded_nodeids = _read_excluded_nodeids()


def pytest_collection_modifyitems(config, items):
    excluded = getattr(config, "_deselect_excluded_nodeids", set())
    if not excluded:
        return

    kept = []
    deselected = []
    for item in items:
        if item.nodeid in excluded:
            deselected.append(item)
        else:
            kept.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept
