#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    updated = text.replace("@pytest.yield_fixture", "@pytest.fixture")
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    candidates = [
        Path("/testbed/tests/conftest.py"),
    ]
    patched = False
    for candidate in candidates:
        if candidate.exists() and patch_file(candidate):
            print(f"patched {candidate}")
            patched = True
    if not patched:
        print("no patch applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
