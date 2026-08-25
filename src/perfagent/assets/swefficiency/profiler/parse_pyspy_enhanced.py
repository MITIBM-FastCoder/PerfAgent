"""
Parser and analyzer for py-spy folded stacks format with richer statistics.

Folded stacks format (one stack trace per line):
    frame1;frame2;frame3 count
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


class Frame(object):
    """A single stack frame."""

    _FUNC_FILE_PATTERN = re.compile(r"^(.+?)\s+\((.+)\)$")

    def __init__(self, function, filename=None, lineno=None):
        # type: (str, Optional[str], Optional[int]) -> None
        self.function = function
        self.filename = filename
        self.lineno = lineno

    @classmethod
    def parse(cls, raw):
        # type: (str) -> Frame
        """Parse a frame string into a Frame object."""
        raw = raw.strip()
        match = cls._FUNC_FILE_PATTERN.match(raw)
        if match:
            function = match.group(1)
            location = match.group(2)
            filename, lineno = cls._parse_location(location)
            if filename is not None:
                return cls(function=function, filename=filename, lineno=lineno)
            return cls(function=function, filename=location)
        return cls(function=raw)

    @staticmethod
    def _parse_location(location):
        # type: (str) -> Tuple[Optional[str], Optional[int]]
        # Split on the last ":" to support Windows paths.
        if ":" not in location:
            return location, None
        head, tail = location.rsplit(":", 1)
        if tail.isdigit():
            return head, int(tail)
        return location, None

    def __str__(self):
        if self.filename is not None and self.lineno is not None:
            return "{0} ({1}:{2})".format(self.function, self.filename, self.lineno)
        if self.filename is not None:
            return "{0} ({1})".format(self.function, self.filename)
        return self.function

    def __eq__(self, other):
        if not isinstance(other, Frame):
            return NotImplemented
        return (self.function, self.filename, self.lineno) == (
            other.function, other.filename, other.lineno)

    def __hash__(self):
        return hash((self.function, self.filename, self.lineno))


class StackTrace(object):
    """A complete stack trace with its sample count."""

    def __init__(self, frames, count):
        # type: (Tuple[Frame, ...], int) -> None
        self.frames = frames
        self.count = count

    @classmethod
    def parse(cls, line):
        # type: (str) -> Optional[StackTrace]
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

    def __str__(self):
        return " -> ".join(str(f) for f in self.frames)


class FunctionStats(object):
    """Aggregated statistics for a function."""

    def __init__(self, function, filename, lineno,
                 self_samples=0, total_samples=0, callers=None, callees=None):
        # type: (str, Optional[str], Optional[int], int, int, Optional[Dict[str, int]], Optional[Dict[str, int]]) -> None
        self.function = function
        self.filename = filename
        self.lineno = lineno
        self.self_samples = self_samples
        self.total_samples = total_samples
        self.callers = callers if callers is not None else defaultdict(int)
        self.callees = callees if callees is not None else defaultdict(int)


class FoldedStacksProfile(object):
    """Analyzer for folded stacks profile data."""

    def __init__(self, stacks=None):
        # type: (Optional[List[StackTrace]]) -> None
        self.stacks = stacks or []  # type: List[StackTrace]
        self._function_stats = None  # type: Optional[Dict[str, FunctionStats]]

    @classmethod
    def load(cls, filepath):
        # type: (Union[str, Path]) -> FoldedStacksProfile
        """Load a folded stacks file."""
        stacks = []
        with open(str(filepath)) as f:
            for line in f:
                stack = StackTrace.parse(line)
                if stack:
                    stacks.append(stack)
        return cls(stacks)

    @property
    def total_samples(self):
        # type: () -> int
        """Total number of samples in the profile."""
        return sum(s.count for s in self.stacks)

    def _build_function_stats(self):
        # type: () -> Dict[str, FunctionStats]
        """Build aggregated statistics for all functions."""
        stats = {}  # type: Dict[str, FunctionStats]

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
    def function_stats(self):
        # type: () -> Dict[str, FunctionStats]
        """Get aggregated statistics for all functions (cached)."""
        if self._function_stats is None:
            self._function_stats = self._build_function_stats()
        return self._function_stats

    def hottest_functions(self, n=10, by="self"):
        # type: (int, str) -> List[FunctionStats]
        """
        Get the n most expensive functions.

        Args:
            n: Number of functions to return.
            by: 'self' or 'total'/'total_stack'.
        """
        if by == "self":
            key_fn = lambda s: s.self_samples
        elif by in ("total", "total_stack"):
            key_fn = lambda s: s.total_samples
        else:
            raise ValueError("Unknown 'by' mode: {0}".format(by))

        sorted_stats = sorted(self.function_stats.values(), key=key_fn, reverse=True)
        return sorted_stats[:n]

    def filter_under_function(self, function_name):
        # type: (str) -> FoldedStacksProfile
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

    def top_stacks(self, n=10):
        # type: (int) -> List[Tuple[str, int]]
        """Return the most frequent full stacks."""
        counts = defaultdict(int)  # type: Dict[str, int]
        for stack in self.stacks:
            counts[str(stack)] += stack.count
        return sorted(counts.items(), key=lambda x: -x[1])[:n]

    def dominant_coverage(self, n=10):
        # type: (int) -> float
        """Percent of samples covered by the top N stacks."""
        total = self.total_samples
        if total == 0:
            return 0.0
        covered = sum(count for _, count in self.top_stacks(n))
        return covered / total * 100.0

    def _aggregate_by_key(self, key_fn):
        agg = {}  # type: Dict[str, Dict[str, int]]
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
    def _is_user_code(filename):
        # type: (Optional[str]) -> bool
        """Return True if the filename represents user code (not a native extension)."""
        if not filename:
            return False
        return ".so" not in filename

    @staticmethod
    def _module_from_filename(filename):
        # type: (Optional[str]) -> str
        if not filename:
            return "<unknown>"
        if filename.endswith(".so"):
            name = filename.rsplit("/", 1)[-1]
            if ".cpython-" in name:
                name = name.split(".cpython-")[0] + ".so"
            return name
        path = filename.replace("\\", "/")
        for marker in ("/site-packages/", "/dist-packages/"):
            if marker in path:
                path = path.split(marker, 1)[1]
                break
        path = path.lstrip("./").lstrip("/")
        if path.endswith(".py"):
            path = path[:-3]
        if path.endswith("/__init__"):
            path = path[:-9]
        return path.replace("/", ".") if path else "<unknown>"

    def file_stats(self):
        # type: () -> Dict[str, Dict[str, int]]
        """Aggregate stats by filename."""
        return self._aggregate_by_key(lambda s: s.filename or "<unknown>")

    def module_stats(self):
        # type: () -> Dict[str, Dict[str, int]]
        """Aggregate stats by module path derived from filename."""
        return self._aggregate_by_key(lambda s: self._module_from_filename(s.filename))

    def edges(self):
        # type: () -> Dict[Tuple[str, str], int]
        """Aggregate caller->callee edges across all functions."""
        edge_map = defaultdict(int)  # type: Dict[Tuple[str, str], int]
        for stats in self.function_stats.values():
            if stats.filename is not None and stats.lineno is not None:
                caller = "{0} ({1}:{2})".format(
                    stats.function, stats.filename, stats.lineno)
            else:
                caller = stats.function
            for callee, count in stats.callees.items():
                edge_map[(caller, callee)] += count
        return edge_map

    def report(self, n=5):
        # type: (int) -> str
        """Generate a text report of the hottest functions."""
        lines = []
        total = self.total_samples

        lines.append("Top hotspots by self time (where CPU is actually spending time)")
        lines.append("")
        lines.append("{0:>6}  {1:<30}  {2:>8}  {3:>8}  Location".format(
            "% time", "Function", "Self", "Total"))
        lines.append("{0}  {1}  {2}  {3}  {4}".format(
            "-" * 6, "-" * 30, "-" * 8, "-" * 8, "-" * 40))

        for stats in self.hottest_functions(n, by="self"):
            self_pct = 100 * stats.self_samples / total if total else 0
            location = "{0}:{1}".format(stats.filename, stats.lineno) if stats.filename else ""
            lines.append(
                "{0:>6.1f}%  {1:<30}  {2:>8}  {3:>8}  {4}".format(
                    self_pct, stats.function,
                    stats.self_samples, stats.total_samples, location))

        lines.append("")
        lines.append("")
        lines.append("Top functions by total time (including calls to other functions)")
        lines.append("")
        lines.append("{0:>6}  {1:<30}  {2:>8}  Location".format(
            "% time", "Function", "Total"))
        lines.append("{0}  {1}  {2}  {3}".format(
            "-" * 6, "-" * 30, "-" * 8, "-" * 40))

        for stats in self.hottest_functions(n + 1, by="total"):
            if stats.function == "workload":
                continue
            total_pct = 100 * stats.total_samples / total if total else 0
            location = stats.filename if stats.filename else ""
            lines.append(
                "{0:>6.1f}%  {1:<30}  {2:>8}  {3}".format(
                    total_pct, stats.function,
                    stats.total_samples, location))

        return "\n".join(lines)

    def to_json(
        self,
        top_n=5,
        top_stacks_n=5,
        top_callers_n=3,
        top_callees_n=3,
        top_files_n=3,
    ):
        total = self.total_samples

        def _top_edges(edge_counts, limit):
            if limit <= 0:
                return []
            rows = []
            for name, count in sorted(edge_counts.items(), key=lambda x: -x[1])[:limit]:
                rows.append(
                    {
                        "function": name,
                        "count": count,
                        "pct_total": (count / total * 100.0) if total else 0.0,
                    }
                )
            return rows

        def stat_row(s):
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
                "is_user_code": self._is_user_code(s.filename),
                "top_callers": _top_edges(s.callers, top_callers_n),
                "top_callees": _top_edges(s.callees, top_callees_n),
            }

        hotspots = {
            "self": [stat_row(s) for s in self.hottest_functions(top_n, by="self")],
            "total": [
                stat_row(s)
                for s in self.hottest_functions(top_n, by="total")
                if s.function != "workload"
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

        file_stats_list = []
        for filename, fstats in sorted(
            self.file_stats().items(), key=lambda x: -x[1]["total_samples"]
        )[:top_files_n]:
            file_stats_list.append(
                {
                    "filename": filename,
                    "self_samples": fstats["self_samples"],
                    "total_samples": fstats["total_samples"],
                    "self_pct": (fstats["self_samples"] / total * 100.0) if total else 0.0,
                    "total_pct": (fstats["total_samples"] / total * 100.0) if total else 0.0,
                    "is_user_code": self._is_user_code(filename),
                }
            )

        module_stats_list = []
        for module, mstats in sorted(
            self.module_stats().items(), key=lambda x: -x[1]["total_samples"]
        ):
            module_stats_list.append(
                {
                    "module": module,
                    "self_samples": mstats["self_samples"],
                    "total_samples": mstats["total_samples"],
                    "self_pct": (mstats["self_samples"] / total * 100.0) if total else 0.0,
                    "total_pct": (mstats["total_samples"] / total * 100.0) if total else 0.0,
                    "is_user_code": ".so" not in module,
                }
            )

        return {
            "total_samples": total,
            "coverage": {"top_stacks_n": top_stacks_n, "pct": self.dominant_coverage(top_stacks_n)},
            "hotspots": hotspots,
            "files": file_stats_list,
            "modules": module_stats_list,
            "top_stacks": stacks,
        }


def _parse_args():
    parser = argparse.ArgumentParser(description="Analyze py-spy folded stacks.")
    parser.add_argument("profile", help="Path to folded stacks profile.")
    parser.add_argument("--report", choices=["text", "json"], default="text")
    parser.add_argument("--top", type=int, default=5, help="Number of top items to show.")
    parser.add_argument("--top-stacks", type=int, default=5, help="Number of top stacks to show.")
    parser.add_argument("--top-callers", type=int, default=3, help="Number of callers per hotspot.")
    parser.add_argument("--top-callees", type=int, default=3, help="Number of callees per hotspot.")
    parser.add_argument("--top-files", type=int, default=3, help="Number of top files to show.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    profile = FoldedStacksProfile.load(args.profile)
    profile = profile.filter_under_function("workload")

    if True or args.report == "json":
        report = profile.to_json(
            top_n=args.top,
            top_stacks_n=args.top_stacks,
            top_callers_n=args.top_callers,
            top_callees_n=args.top_callees,
            top_files_n=args.top_files,
        )
        print(json.dumps(report, indent=2))
    else:
        print(profile.report(n=args.top))
