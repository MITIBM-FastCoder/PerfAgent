"""
Parser and analyzer for py-spy folded stacks format.

The folded stacks format has one stack trace per line:
    frame1;frame2;frame3 count

py-spy frames typically look like:
    function_name (filename.py:lineno)
    native_symbol (module.so)
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class Frame:
    """A single stack frame."""
    function: str
    filename: str | None = None
    lineno: int | None = None

    # Python frames look like "function_name (file.py:123)".
    _LINE_PATTERN = re.compile(r'^(.+?)\s+\((.+):(\d+)\)$')
    # Native frames often look like "symbol_name (module.so)".
    _FILE_PATTERN = re.compile(r'^(.+?)\s+\((.+)\)$')

    @classmethod
    def parse(cls, raw: str) -> Frame:
        """Parse a frame string into a Frame object."""
        raw = raw.strip()
        match = cls._LINE_PATTERN.match(raw)
        if match:
            return cls(
                function=match.group(1),
                filename=match.group(2),
                lineno=int(match.group(3))
            )

        match = cls._FILE_PATTERN.match(raw)
        if match:
            return cls(
                function=match.group(1),
                filename=match.group(2),
            )

        # Fallback: just a function name
        return cls(function=raw)

    @property
    def location(self) -> str:
        """Return the best available location for this frame."""
        if self.filename and self.lineno:
            return f"{self.filename}:{self.lineno}"
        if self.filename:
            return self.filename
        return self.function

    def __str__(self) -> str:
        if self.filename and self.lineno:
            return f"{self.function} ({self.filename}:{self.lineno})"
        if self.filename:
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
        if not line or line.startswith('#'):
            return None

        # Split on last space to get count
        parts = line.rsplit(' ', 1)
        if len(parts) != 2:
            return None

        try:
            count = int(parts[1])
        except ValueError:
            return None

        frames = tuple(Frame.parse(f) for f in parts[0].split(';'))
        return cls(frames=frames, count=count)

    @property
    def leaf(self) -> Frame:
        """The top of the stack (the function that was executing)."""
        return self.frames[-1]

    @property
    def root(self) -> Frame:
        """The bottom of the stack (usually main/entry point)."""
        return self.frames[0]

    def __str__(self) -> str:
        return ' -> '.join(str(f) for f in self.frames)


@dataclass
class FunctionStats:
    """Aggregated statistics for a function."""
    function: str
    filename: str | None
    lineno: int | None
    self_samples: int = 0  # samples where this function was at top of stack
    total_samples: int = 0  # samples where this function appeared anywhere
    callers: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    callees: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def location(self) -> str:
        if self.filename and self.lineno:
            return f"{self.filename}:{self.lineno}"
        if self.filename:
            return self.filename
        return self.function

    @property
    def estimated_calls(self) -> int:
        """
        Estimate how many times this function was called.

        Uses sum of caller edge counts. For root functions (no callers),
        falls back to total_samples.
        """
        if self.callers:
            return sum(self.callers.values())
        return self.total_samples


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

    @classmethod
    def parse(cls, content: str) -> FoldedStacksProfile:
        """Parse folded stacks from a string."""
        stacks = []
        for line in content.strip().split('\n'):
            stack = StackTrace.parse(line)
            if stack:
                stacks.append(stack)
        return cls(stacks)

    @property
    def total_samples(self) -> int:
        """Total number of samples in the profile."""
        return sum(s.count for s in self.stacks)

    @staticmethod
    def _frame_matches(
        frame: Frame,
        function_name: str,
        filename_substring: str | None = None
    ) -> bool:
        """Check whether a frame matches a function and optional filename."""
        if frame.function != function_name:
            return False
        if filename_substring is None:
            return True
        return frame.filename is not None and filename_substring in frame.filename


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
                        lineno=frame.lineno
                    )

                # Self time: only if at top of stack
                if i == len(stack.frames) - 1:
                    stats[key].self_samples += stack.count

                # Total time: count once per stack
                if key not in seen_in_stack:
                    stats[key].total_samples += stack.count
                    seen_in_stack.add(key)

                # Track callers (who called this function)
                if i > 0:
                    caller = str(stack.frames[i - 1])
                    stats[key].callers[caller] += stack.count

                # Track callees (who this function called)
                if i < len(stack.frames) - 1:
                    callee = str(stack.frames[i + 1])
                    stats[key].callees[callee] += stack.count

        return stats

    @property
    def function_stats(self) -> dict[str, FunctionStats]:
        """Get aggregated statistics for all functions (cached)."""
        if self._function_stats is None:
            self._function_stats = self._build_function_stats()
        return self._function_stats

    def hottest_functions(
        self,
        n: int = 10,
        by: str = 'self'
    ) -> list[FunctionStats]:
        """
        Get the n most expensive functions.

        Args:
            n: Number of functions to return
            by: 'self' for self-time, 'total' for total time

        Both modes preserve line-level granularity when line numbers are
        available so reports can point back to specific source locations.
        """
        key_fn = (
            (lambda s: s.self_samples)
            if by == 'self'
            else (lambda s: s.total_samples)
        )
        sorted_stats = sorted(
            self.function_stats.values(),
            key=key_fn,
            reverse=True
        )
        return sorted_stats[:n]

    def find_function(self, pattern: str) -> list[FunctionStats]:
        """Find functions matching a regex pattern."""
        regex = re.compile(pattern)
        return [
            s for s in self.function_stats.values()
            if regex.search(s.function) or
               (s.filename and regex.search(s.filename))
        ]

    def stacks_containing(self, pattern: str) -> Iterator[StackTrace]:
        """Yield all stacks containing a function matching the pattern."""
        regex = re.compile(pattern)
        for stack in self.stacks:
            for frame in stack.frames:
                if regex.search(frame.function) or \
                   (frame.filename and regex.search(frame.filename)):
                    yield stack
                    break

    def callers_of(self, pattern: str) -> dict[str, int]:
        """Get all callers of functions matching the pattern."""
        callers: dict[str, int] = defaultdict(int)
        for stats in self.find_function(pattern):
            for caller, count in stats.callers.items():
                callers[caller] += count
        return dict(sorted(callers.items(), key=lambda x: -x[1]))

    def callees_of(self, pattern: str) -> dict[str, int]:
        """Get all functions called by functions matching the pattern."""
        callees: dict[str, int] = defaultdict(int)
        for stats in self.find_function(pattern):
            for callee, count in stats.callees.items():
                callees[callee] += count
        return dict(sorted(callees.items(), key=lambda x: -x[1]))

    def filter(
        self,
        include: str | None = None,
        exclude: str | None = None
    ) -> FoldedStacksProfile:
        """
        Create a new profile with filtered stacks.

        Args:
            include: Only include stacks matching this pattern
            exclude: Exclude stacks matching this pattern
        """
        include_re = re.compile(include) if include else None
        exclude_re = re.compile(exclude) if exclude else None

        filtered = []
        for stack in self.stacks:
            stack_str = str(stack)

            if include_re and not include_re.search(stack_str):
                continue
            if exclude_re and exclude_re.search(stack_str):
                continue

            filtered.append(stack)

        return FoldedStacksProfile(filtered)

    def filter_under_function(
        self,
        function_name: str,
        filename_substring: str | None = None
    ) -> FoldedStacksProfile:
        """
        Filter to only include frames called under a specific function.

        This finds stacks containing the specified function and trims them
        to only include that function and everything it calls (frames after
        it in the stack).

        Args:
            function_name: The function name to filter under (exact match)
            filename_substring: Optional filename substring to disambiguate
                functions with the same name

        Returns:
            A new profile with trimmed stacks
        """
        filtered = []
        for stack in self.stacks:
            # Find the index of the target function in the stack
            target_idx = None
            for i, frame in enumerate(stack.frames):
                if self._frame_matches(frame, function_name, filename_substring):
                    target_idx = i
                    break

            if target_idx is not None:
                # Keep frames from target function onwards (inclusive)
                trimmed_frames = stack.frames[target_idx:]
                filtered.append(StackTrace(frames=trimmed_frames, count=stack.count))

        return FoldedStacksProfile(filtered)

    def exclude_under_function(
        self,
        function_name: str,
        filename_substring: str | None = None
    ) -> FoldedStacksProfile:
        """
        Exclude any stack that is currently executing under a specific function.

        Because folded stacks represent a single call chain sample, dropping any
        stack that contains `function_name` removes that function and everything
        it called at the time of sampling.

        Args:
            function_name: The function name to exclude (exact match)
            filename_substring: Optional filename substring to disambiguate
                functions with the same name

        Returns:
            A new profile without matching stacks
        """
        filtered = []
        for stack in self.stacks:
            if any(
                self._frame_matches(frame, function_name, filename_substring)
                for frame in stack.frames
            ):
                continue
            filtered.append(stack)

        return FoldedStacksProfile(filtered)

    def report(self, n: int = 5) -> str:
        """Generate a text report of the hottest functions."""
        lines = []
        total = self.total_samples

        # Self time - where CPU is actually spending time
        lines.append("Top hotspots by self time (where CPU is actually spending time)")
        lines.append("")
        lines.append(f"{'% time':>6}  {'Function':<30}  Location")
        lines.append(f"{'-'*6}  {'-'*30}  {'-'*40}")

        for stats in self.hottest_functions(n, by='self'):
            self_pct = 100 * stats.self_samples / total if total else 0
            lines.append(f"{self_pct:>6.1f}%  {stats.function:<30}  {stats.location}")

        # Total time - includes time spent in called functions
        lines.append("")
        lines.append("")
        lines.append("Top functions by total time (including calls to other functions)")
        lines.append("")
        lines.append(f"{'% time':>6}  {'Function':<30}  Location")
        lines.append(f"{'-'*6}  {'-'*30}  {'-'*40}")

        # n + 1 here since we exclude `experiment` which is going to be here
        for stats in self.hottest_functions(n + 1, by='total'):
            if stats.function == "experiment":
                continue
            total_pct = 100 * stats.total_samples / total if total else 0
            lines.append(f"{total_pct:>6.1f}%  {stats.function:<30}  {stats.location}")

        return '\n'.join(lines)


# Convenience function
def load(filepath: str | Path) -> FoldedStacksProfile:
    """Load a folded stacks file."""
    return FoldedStacksProfile.load(filepath)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Analyze py-spy folded stacks.")
    parser.add_argument("profile", help="Path to folded stacks profile.")
    parser.add_argument(
        "--under",
        default="experiment",
        help="Keep only stacks under this function. Use an empty string to skip."
    )
    parser.add_argument(
        "--exclude-under",
        action="append",
        default=[],
        help="Drop any stack that contains this function. Can be repeated."
    )
    parser.add_argument(
        "--filename-substring",
        help="Only match frames whose filename contains this substring."
    )
    args = parser.parse_args()

    profile = FoldedStacksProfile.load(args.profile)
    if args.under:
        default_filename_substring = args.filename_substring
        if default_filename_substring is None and args.under == "experiment":
            default_filename_substring = "perf_script.py"
        profile = profile.filter_under_function(
            args.under,
            filename_substring=default_filename_substring,
        )
        if args.under == "experiment" and "setup" not in args.exclude_under:
            profile = profile.exclude_under_function(
                "setup",
                filename_substring=default_filename_substring,
            )
    for function_name in args.exclude_under:
        profile = profile.exclude_under_function(
            function_name,
            filename_substring=args.filename_substring,
        )
    print(profile.report())
