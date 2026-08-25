"""
Parser and analyzer for py-spy folded stacks format with richer statistics.

Folded stacks format (one stack trace per line):
    frame1;frame2;frame3 count
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = "/testbed"
REPO_ROOT_PREFIX = f"{REPO_ROOT}/"
REPO_ROOT_PATH = Path(REPO_ROOT)
PACKAGE_PATH_MARKERS = (
    "/site-packages/",
    "/dist-packages/",
    "site-packages/",
    "dist-packages/",
)
PREFERRED_SOURCE_PREFIXES = (
    "src/",
    "python/",
    "lib/",
)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


@lru_cache(maxsize=1)
def _repo_source_files() -> tuple[str, ...]:
    files: list[str] = []
    try:
        for entry in REPO_ROOT_PATH.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_file():
                files.append(entry.name)
                continue
            if not entry.is_dir():
                continue
            for path in entry.rglob("*"):
                if path.is_file():
                    files.append(path.relative_to(REPO_ROOT_PATH).as_posix())
    except OSError:
        return tuple()
    return tuple(sorted(set(files)))


@lru_cache(maxsize=1)
def _repo_source_file_set() -> frozenset[str]:
    return frozenset(_repo_source_files())


@lru_cache(maxsize=1)
def _repo_source_files_by_basename() -> dict[str, tuple[str, ...]]:
    files_by_basename: dict[str, list[str]] = defaultdict(list)
    for relpath in _repo_source_files():
        files_by_basename[Path(relpath).name].append(relpath)
    return {
        basename: tuple(sorted(paths))
        for basename, paths in files_by_basename.items()
    }


@lru_cache(maxsize=None)
def _resolve_repo_relpath(relpath: str) -> str:
    """Try to resolve *relpath* to an actual file in the repo.

    Handles the common case where py-spy reports ``datasets/foo.py`` but the
    repo stores the file at ``src/datasets/foo.py``.
    """
    relpath = relpath.lstrip("./").lstrip("/")
    if not relpath:
        return relpath

    repo_files = _repo_source_file_set()

    # Direct match
    if relpath in repo_files:
        return relpath

    # Try common source prefixes (src/, python/, lib/)
    for prefix in PREFERRED_SOURCE_PREFIXES:
        candidate = f"{prefix}{relpath}"
        if candidate in repo_files:
            return candidate

    # Basename-only lookup (only if unambiguous)
    if "/" not in relpath:
        matches = _repo_source_files_by_basename().get(relpath, ())
        if len(matches) == 1:
            return matches[0]

    # Suffix match: find repo files ending with /relpath
    suffix = f"/{relpath}"
    suffix_matches = [
        p for p in _repo_source_files()
        if p.endswith(suffix) and not p.startswith(("build/", "dist/", "__pycache__/"))
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return relpath


def _normalize_repo_filename(filename: str | None) -> str | None:
    if not filename:
        return None

    path = _normalize_path(filename)
    if not path:
        return None
    if path.endswith(".so"):
        return path

    if path.startswith(REPO_ROOT_PREFIX):
        path = path[len(REPO_ROOT_PREFIX) :].lstrip("/")
        if not path:
            return None

    for marker in PACKAGE_PATH_MARKERS:
        if marker in path:
            relpath = path.split(marker, 1)[1].lstrip("/")
            if not relpath:
                return None
            return _resolve_repo_relpath(relpath)

    if path.startswith("/"):
        return path

    relpath = path.lstrip("./")
    if not relpath:
        return None
    return _resolve_repo_relpath(relpath)


@dataclass(frozen=True)
class Frame:
    """A single stack frame."""

    function: str
    filename: str | None = None
    lineno: int | None = None

    _FUNC_FILE_PATTERN = re.compile(r"^(.+?)\s+\((.+)\)$")

    @classmethod
    def parse(cls, raw: str) -> Frame:
        """Parse a frame string into a Frame object."""
        raw = raw.strip()
        match = cls._FUNC_FILE_PATTERN.match(raw)
        if match:
            function = match.group(1)
            location = match.group(2)
            filename, lineno = cls._parse_location(location)
            if filename is not None:
                return cls(
                    function=function,
                    filename=_normalize_repo_filename(filename),
                    lineno=lineno,
                )
            return cls(function=function, filename=_normalize_repo_filename(location))
        return cls(function=raw)

    @staticmethod
    def _parse_location(location: str) -> tuple[str | None, int | None]:
        # Split on the last ":" to support Windows paths.
        if ":" not in location:
            return location, None
        head, tail = location.rsplit(":", 1)
        if tail.isdigit():
            return head, int(tail)
        return location, None

    def __str__(self) -> str:
        if self.filename is not None and self.lineno is not None:
            return f"{self.function} ({self.filename}:{self.lineno})"
        if self.filename is not None:
            return f"{self.function} ({self.filename})"
        return self.function


@dataclass
class StackTrace:
    """A complete stack trace with its sample count."""

    frames: tuple[Frame, ...]
    count: int

    @classmethod
    def parse(cls, line: str) -> StackTrace | None:
        """Parse a folded stack line into a StackTrace."""
        line = line.strip()
        if not line or line.startswith("#"):
            return None

        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            return None

        try:
            count = int(parts[1])
        except ValueError:
            return None

        frames = tuple(Frame.parse(f) for f in parts[0].split(";"))
        return cls(frames=frames, count=count)

    def __str__(self) -> str:
        return " -> ".join(str(f) for f in self.frames)


@dataclass
class FunctionStats:
    """Aggregated statistics for a function."""

    function: str
    filename: str | None
    lineno: int | None
    self_samples: int = 0
    total_samples: int = 0
    callers: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    callees: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class FoldedStacksProfile:
    """Analyzer for folded stacks profile data."""

    def __init__(self, stacks: list[StackTrace] | None = None):
        self.stacks: list[StackTrace] = stacks or []
        self._function_stats: dict[str, FunctionStats] | None = None

    @classmethod
    def load(cls, filepath: str | Path) -> FoldedStacksProfile:
        """Load a folded stacks file."""
        stacks = []
        with open(filepath) as f:
            for line in f:
                stack = StackTrace.parse(line)
                if stack:
                    stacks.append(stack)
        return cls(stacks)

    @property
    def total_samples(self) -> int:
        """Total number of samples in the profile."""
        return sum(s.count for s in self.stacks)

    def _build_function_stats(self) -> dict[str, FunctionStats]:
        """Build aggregated statistics for all functions."""
        stats: dict[str, FunctionStats] = {}

        for stack in self.stacks:
            seen_in_stack = set()

            for i, frame in enumerate(stack.frames):
                key = str(frame)

                if key not in stats:
                    stats[key] = FunctionStats(
                        function=frame.function,
                        filename=frame.filename,
                        lineno=frame.lineno,
                    )

                current = stats[key]

                if i == len(stack.frames) - 1:
                    current.self_samples += stack.count

                if key not in seen_in_stack:
                    current.total_samples += stack.count
                    seen_in_stack.add(key)

                if i > 0:
                    caller = str(stack.frames[i - 1])
                    current.callers[caller] += stack.count

                if i < len(stack.frames) - 1:
                    callee = str(stack.frames[i + 1])
                    current.callees[callee] += stack.count

        return stats

    @property
    def function_stats(self) -> dict[str, FunctionStats]:
        """Get aggregated statistics for all functions (cached)."""
        if self._function_stats is None:
            self._function_stats = self._build_function_stats()
        return self._function_stats

    def hottest_functions(self, n: int = 10, by: str = "self") -> list[FunctionStats]:
        """
        Get the n most expensive functions.

        Args:
            n: Number of functions to return.
            by: 'self' or 'total'.
        """
        if by == "self":
            key_fn = lambda s: s.self_samples
        elif by == "total":
            key_fn = lambda s: s.total_samples
        else:
            raise ValueError(f"Unknown 'by' mode: {by}")

        sorted_stats = sorted(self.function_stats.values(), key=key_fn, reverse=True)
        return sorted_stats[:n]

    def hottest_repo_functions(self, n: int = 10, by: str = "self") -> list[FunctionStats]:
        """Get the hottest functions rooted in the /testbed repository."""
        if by == "self":
            key_fn = lambda s: s.self_samples
        elif by == "total":
            key_fn = lambda s: s.total_samples
        else:
            raise ValueError(f"Unknown 'by' mode: {by}")

        repo_stats = [
            stats for stats in self.function_stats.values() if self._is_repo_code(stats.filename)
        ]
        return sorted(repo_stats, key=key_fn, reverse=True)[:n]

    def filter_under_function(self, function_name: str) -> FoldedStacksProfile:
        """
        Filter to only include frames called under a specific function.
        """
        filtered = []
        for stack in self.stacks:
            target_idx = None
            for i, frame in enumerate(stack.frames):
                if frame.function == function_name:
                    target_idx = i
                    break

            if target_idx is not None:
                trimmed_frames = stack.frames[target_idx:]
                filtered.append(StackTrace(frames=trimmed_frames, count=stack.count))

        return FoldedStacksProfile(filtered)

    def exclude_under_function(self, function_name: str) -> FoldedStacksProfile:
        """
        Exclude any stack that is currently executing under a specific function.
        """
        filtered = []
        for stack in self.stacks:
            if any(frame.function == function_name for frame in stack.frames):
                continue
            filtered.append(stack)

        return FoldedStacksProfile(filtered)

    def top_stacks(self, n: int = 10) -> list[tuple[str, int]]:
        """Return the most frequent full stacks."""
        counts: dict[str, int] = defaultdict(int)
        for stack in self.stacks:
            counts[str(stack)] += stack.count
        return sorted(counts.items(), key=lambda x: -x[1])[:n]

    def dominant_coverage(self, n: int = 10) -> float:
        """Percent of samples covered by the top N stacks."""
        total = self.total_samples
        if total == 0:
            return 0.0
        covered = sum(count for _, count in self.top_stacks(n))
        return covered / total * 100.0

    def _aggregate_by_key(self, key_fn) -> dict[str, dict[str, int]]:
        agg: dict[str, dict[str, int]] = {}
        for stats in self.function_stats.values():
            key = key_fn(stats)
            if key not in agg:
                agg[key] = {
                    "self_samples": 0,
                    "total_samples": 0,
                }
            agg[key]["self_samples"] += stats.self_samples
            agg[key]["total_samples"] += stats.total_samples
        return agg

    @staticmethod
    def _is_user_code(filename: str | None) -> bool:
        """Return True if the filename represents user code (not a native extension)."""
        if not filename:
            return False
        return ".so" not in filename

    @staticmethod
    def _is_repo_code(filename: str | None) -> bool:
        """Return True if the filename is inside the repository checkout."""
        if not filename:
            return False

        path = _normalize_repo_filename(filename)
        if not path:
            return False
        if path.endswith(".so"):
            return False

        if path.startswith("/") or path.startswith(".venv/"):
            return False

        return path in _repo_source_file_set()

    @staticmethod
    def _is_repo_frame_name(name: str) -> bool:
        """Best-effort check for whether a stringified frame points into /testbed."""
        return FoldedStacksProfile._is_repo_code(Frame.parse(name).filename)

    @staticmethod
    def _module_from_filename(filename: str | None) -> str:
        if not filename:
            return "<unknown>"
        path = _normalize_repo_filename(filename)
        if not path:
            return "<unknown>"
        if path.endswith(".so"):
            name = path.rsplit("/", 1)[-1]
            if ".cpython-" in name:
                name = name.split(".cpython-")[0] + ".so"
            return name
        path = path.lstrip("./").lstrip("/")
        if path.endswith(".py"):
            path = path[:-3]
        if path.endswith("/__init__"):
            path = path[:-9]
        return path.replace("/", ".") if path else "<unknown>"

    def file_stats(self) -> dict[str, dict[str, int]]:
        """Aggregate stats by filename."""
        return self._aggregate_by_key(lambda s: s.filename or "<unknown>")

    def module_stats(self) -> dict[str, dict[str, int]]:
        """Aggregate stats by module path derived from filename."""
        return self._aggregate_by_key(lambda s: self._module_from_filename(s.filename))

    def repo_file_stats(self) -> dict[str, dict[str, int]]:
        """Aggregate stats by filename for files inside /testbed only."""
        return self._aggregate_by_key(
            lambda s: s.filename if self._is_repo_code(s.filename) else None
        )

    def repo_module_stats(self) -> dict[str, dict[str, int]]:
        """Aggregate stats by module path for files inside /testbed only."""
        return self._aggregate_by_key(
            lambda s: self._module_from_filename(s.filename)
            if self._is_repo_code(s.filename)
            else None
        )

    def report(self, n: int = 5) -> str:
        """Generate a text report of the hottest functions."""
        lines = []
        total = self.total_samples

        lines.append("Top /testbed hotspots by self time (where CPU is actually spending time)")
        lines.append("")
        lines.append(f"{'% time':>6}  {'Function':<30}  {'Self':>8}  {'Total':>8}  Location")
        lines.append(f"{'-'*6}  {'-'*30}  {'-'*8}  {'-'*8}  {'-'*40}")

        for stats in self.hottest_repo_functions(n, by="self"):
            self_pct = 100 * stats.self_samples / total if total else 0
            location = f"{stats.filename}:{stats.lineno}" if stats.filename else ""
            lines.append(
                f"{self_pct:>6.1f}%  {stats.function:<30}  "
                f"{stats.self_samples:>8}  {stats.total_samples:>8}  {location}"
            )

        lines.append("")
        lines.append("")
        lines.append("Top /testbed functions by total time (including calls to other functions)")
        lines.append("")
        lines.append(f"{'% time':>6}  {'Function':<30}  {'Total':>8}  Location")
        lines.append(f"{'-'*6}  {'-'*30}  {'-'*8}  {'-'*40}")

        for stats in self.hottest_repo_functions(n + 1, by="total"):
            if stats.function == "experiment":
                continue
            total_pct = 100 * stats.total_samples / total if total else 0
            location = f"{stats.filename}" if stats.filename else ""
            lines.append(
                f"{total_pct:>6.1f}%  {stats.function:<30}  "
                f"{stats.total_samples:>8}  {location}"
            )

        return "\n".join(lines)

    def to_json(
        self,
        top_n: int = 5,
        top_stacks_n: int = 5,
        top_callers_n: int = 3,
        top_callees_n: int = 3,
        top_files_n: int = 3,
        top_modules_n: int = 5,
    ) -> dict:
        total = self.total_samples

        def _top_edges(edge_counts: dict[str, int], limit: int) -> list[dict[str, float | int | str | bool]]:
            if limit <= 0:
                return []
            rows = []
            for name, count in sorted(edge_counts.items(), key=lambda x: -x[1])[:limit]:
                rows.append(
                    {
                        "function": name,
                        "count": count,
                        "pct_total": (count / total * 100.0) if total else 0.0,
                        "in_repo": self._is_repo_frame_name(name),
                    }
                )
            return rows

        def stat_row(s: FunctionStats) -> dict:
            return {
                "function": s.function,
                "filename": s.filename,
                "lineno": s.lineno,
                "self_samples": s.self_samples,
                "total_samples": s.total_samples,
                "self_pct": (s.self_samples / total * 100.0) if total else 0.0,
                "total_pct": (s.total_samples / total * 100.0) if total else 0.0,
                "self_over_total": (
                    s.self_samples / s.total_samples if s.total_samples else 0.0
                ),
                "in_repo": self._is_repo_code(s.filename),
                "top_callers": _top_edges(s.callers, top_callers_n),
                "top_callees": _top_edges(s.callees, top_callees_n),
            }

        hotspots = {
            "self": [stat_row(s) for s in self.hottest_repo_functions(top_n, by="self")],
            "total": [
                stat_row(s)
                for s in self.hottest_repo_functions(top_n, by="total")
                if s.function != "experiment"
            ],
        }

        stacks = []
        for stack, count in self.top_stacks(top_stacks_n):
            stacks.append(
                {
                    "stack": stack,
                    "count": count,
                    "pct": (count / total * 100.0) if total else 0.0,
                }
            )

        file_stats = []
        for filename, stats in sorted(
            self.repo_file_stats().items(), key=lambda x: -x[1]["total_samples"]
        )[:top_files_n]:
            if filename is None:
                continue
            file_stats.append(
                {
                    "filename": filename,
                    "self_samples": stats["self_samples"],
                    "total_samples": stats["total_samples"],
                    "self_pct": (stats["self_samples"] / total * 100.0) if total else 0.0,
                    "total_pct": (stats["total_samples"] / total * 100.0) if total else 0.0,
                }
            )

        module_stats = []
        for module, stats in sorted(
            self.repo_module_stats().items(), key=lambda x: -x[1]["total_samples"]
        )[:top_modules_n]:
            if module is None:
                continue
            module_stats.append(
                {
                    "module": module,
                    "self_samples": stats["self_samples"],
                    "total_samples": stats["total_samples"],
                    "self_pct": (stats["self_samples"] / total * 100.0) if total else 0.0,
                    "total_pct": (stats["total_samples"] / total * 100.0) if total else 0.0,
                }
            )

        return {
            "total_samples": total,
            "coverage": {"top_stacks_n": top_stacks_n, "pct": self.dominant_coverage(top_stacks_n)},
            "hotspots": hotspots,
            "files": file_stats,
            "modules": module_stats,
            "top_stacks": stacks,
        }


def load(filepath: str | Path) -> FoldedStacksProfile:
    """Load a folded stacks file."""
    return FoldedStacksProfile.load(filepath)


@lru_cache(maxsize=1)
def _repo_top_level_entries() -> set[str]:
    """Best-effort snapshot of top-level entries in the checked-out repository."""
    try:
        return {entry.name for entry in REPO_ROOT_PATH.iterdir() if not entry.name.startswith(".")}
    except OSError:
        return set()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze py-spy folded stacks.")
    parser.add_argument("profile", help="Path to folded stacks profile.")
    parser.add_argument("--report", choices=["text", "json"], default="text")
    parser.add_argument("--top", type=int, default=5, help="Number of top items to show.")
    parser.add_argument("--top-stacks", type=int, default=5, help="Number of top stacks to show.")
    parser.add_argument("--top-callers", type=int, default=3, help="Number of callers per hotspot.")
    parser.add_argument("--top-callees", type=int, default=3, help="Number of callees per hotspot.")
    parser.add_argument("--top-files", type=int, default=3, help="Number of top files to show.")
    parser.add_argument("--top-modules", type=int, default=5, help="Number of top modules to show.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    profile = FoldedStacksProfile.load(args.profile)
    profile = profile.filter_under_function("experiment")
    profile = profile.exclude_under_function("setup")

    if True or args.report == "json":
        report = profile.to_json(
            top_n=args.top,
            top_stacks_n=args.top_stacks,
            top_callers_n=args.top_callers,
            top_callees_n=args.top_callees,
            top_files_n=args.top_files,
            top_modules_n=args.top_modules,
        )
        print(json.dumps(report, indent=2))
    else:
        print(profile.report(n=args.top))
