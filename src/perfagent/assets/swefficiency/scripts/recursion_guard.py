# recursion_guard.py
import os
import sys

SAFE_LIMIT = int(os.getenv("PYTEST_RECURSION_LIMIT", "500"))

_original_setrecursionlimit = sys.setrecursionlimit

def _capped_setrecursionlimit(limit):
    _original_setrecursionlimit(min(int(limit), SAFE_LIMIT))

sys.setrecursionlimit = _capped_setrecursionlimit
_original_setrecursionlimit(SAFE_LIMIT)

def _enforce():
    if sys.getrecursionlimit() != SAFE_LIMIT:
        _original_setrecursionlimit(SAFE_LIMIT)

def pytest_sessionstart(session):
    _enforce()

def pytest_runtest_setup(item):
    _enforce()

def pytest_runtest_teardown(item, nextitem):
    _enforce()