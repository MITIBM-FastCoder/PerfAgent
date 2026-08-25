#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def fallback_block() -> list[str]:
    return [
        "try:\n",
        "    from _pytest.doctest import import_path\n",
        "except ImportError:\n",
        "    from _pytest.pathlib import import_path\n",
    ]


def strip_import_path_from_line(line: str) -> str:
    if "import_path" not in line:
        return line

    newline = "\n" if line.endswith("\n") else ""
    content = line[:-1] if newline else line
    indent = content[: len(content) - len(content.lstrip())]
    pieces = [piece.strip() for piece in content.strip().split(",")]
    filtered = [piece for piece in pieces if piece and piece != "import_path"]
    if not filtered:
        return ""
    return f"{indent}{', '.join(filtered)}{newline}"


def patch_file(path: Path) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    for i, line in enumerate(lines):
        if not line.lstrip().startswith("from _pytest.doctest import"):
            continue

        if "import_path" not in "".join(lines[i:i + 20]):
            continue

        if "(" in line:
            j = i + 1
            while j < len(lines) and lines[j].strip() != ")":
                j += 1
            if j >= len(lines):
                return False

            block = lines[i : j + 1]
            if not any("import_path" in block_line for block_line in block):
                continue

            new_block = [block[0]]
            for block_line in block[1:-1]:
                cleaned = strip_import_path_from_line(block_line)
                if cleaned:
                    new_block.append(cleaned)
            new_block.append(block[-1])
            replacement = new_block + ["\n"] + fallback_block()
            lines[i : j + 1] = replacement
            path.write_text("".join(lines), encoding="utf-8")
            return True

        if "import_path" in line:
            cleaned = strip_import_path_from_line(line)
            replacement = []
            if cleaned:
                replacement.append(cleaned)
            replacement.extend(fallback_block())
            lines[i : i + 1] = replacement
            path.write_text("".join(lines), encoding="utf-8")
            return True

    return False


def iter_candidates(scope: str) -> list[Path]:
    candidates = []

    if scope in {"all", "installed"}:
        site_packages = sorted(
            Path("/testbed/.venv").glob("lib/python*/site-packages/transformers/testing_utils.py")
        )
        candidates.extend(site_packages)

    if scope in {"all", "source"}:
        for rel_path in (
            "src/transformers/testing_utils.py",
            "transformers/testing_utils.py",
        ):
            candidate = Path("/testbed") / rel_path
            if candidate.exists():
                candidates.append(candidate)

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
        help="which transformers testing_utils copy to patch",
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
