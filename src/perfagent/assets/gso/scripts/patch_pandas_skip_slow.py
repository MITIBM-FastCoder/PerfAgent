#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


GETOPTION_PATTERN = re.compile(
    r'config\.getoption\(\s*([\'"]--[^\'"]+[\'"])\s*\)'
)

OPTION_DEFAULTS = {
    "--skip-slow": "True",
    "--only-slow": "False",
    "--skip-network": "True",
    "--skip-db": "True",
    "--strict-data-files": "False",
    "--run-high-memory": "False",
}


def replacement(match: re.Match[str]) -> str:
    quoted_option = match.group(1)
    option = quoted_option[1:-1]
    default = OPTION_DEFAULTS.get(option, "False")
    return f"config.getoption({quoted_option}, default={default})"


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    updated = GETOPTION_PATTERN.sub(replacement, text)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def iter_candidates(scope: str) -> list[Path]:
    candidates = []

    if scope in {"all", "installed"}:
        site_packages = sorted(
            Path("/testbed/.venv").glob("lib/python*/site-packages/pandas/conftest.py")
        )
        candidates.extend(site_packages)

    if scope in {"all", "source"}:
        source_candidate = Path("/testbed/pandas/conftest.py")
        if source_candidate.exists():
            candidates.append(source_candidate)

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)
    return unique_candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scope",
        choices=("all", "installed", "source"),
        default="all",
        help="which pandas conftest copy to patch",
    )
    args = parser.parse_args()

    patched = []
    for candidate in iter_candidates(args.scope):
        if patch_file(candidate):
            patched.append(candidate)

    if patched:
        for path in patched:
            print(f"patched {path}")
    else:
        print("no patch applied")

    return 0


if __name__ == "__main__":
    sys.exit(main())
