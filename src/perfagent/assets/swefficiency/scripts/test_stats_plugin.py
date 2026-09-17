"""Collect pytest selection and execution stats for swefficiency test runs."""

import json
import os
from pathlib import Path

_CONFIG = None


def _is_xdist_worker(config) -> bool:
    return hasattr(config, "workerinput")


def _write_stats(config) -> None:
    output_path = getattr(config, "_test_stats_output", None)
    if not output_path or _is_xdist_worker(config):
        return

    payload = {
        "collected_count": len(getattr(config, "_test_stats_collected", [])),
        "executed_count": len(getattr(config, "_test_stats_executed", set())),
    }
    Path(output_path).write_text(json.dumps(payload), encoding="utf-8")


def pytest_configure(config):
    global _CONFIG
    _CONFIG = config
    config._test_stats_output = os.environ.get("TEST_STATS_OUTPUT")
    config._test_stats_collected = []
    config._test_stats_executed = set()
    _write_stats(config)


def pytest_collection_finish(session):
    config = session.config
    if _is_xdist_worker(config):
        return

    config._test_stats_collected = [item.nodeid for item in session.items]
    _write_stats(config)


def pytest_runtest_logreport(report):
    config = _CONFIG
    if config is None:
        return
    if _is_xdist_worker(config):
        return

    config._test_stats_executed.add(report.nodeid)


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if not getattr(config, "_test_stats_collected", None):
        collected_count = getattr(session, "testscollected", 0)
        config._test_stats_collected = [None] * collected_count
    _write_stats(config)
