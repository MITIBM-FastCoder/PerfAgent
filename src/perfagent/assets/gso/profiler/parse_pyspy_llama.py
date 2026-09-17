"""
Llama-specific parser for py-spy folded stacks.

This variant can symbolize native address frames like:
    0x7abc1234 (llama_cpp/libllama.so)

It uses a saved /proc/<pid>/maps snapshot and addr2line to resolve them.
"""

from __future__ import annotations
import os
import re
import subprocess
from bisect import bisect_right
from dataclasses import dataclass, field
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Optional


@dataclass(frozen=True)
class Frame:
    function: str
    filename: Optional[str] = None
    lineno: Optional[int] = None

    _LINE_PATTERN = re.compile(r'^(.+?)\s+\((.+):(\d+)\)$')
    _FILE_PATTERN = re.compile(r'^(.+?)\s+\((.+)\)$')

    @classmethod
    def parse(cls, raw: str) -> Frame:
        raw = raw.strip()
        match = cls._LINE_PATTERN.match(raw)
        if match:
            return cls(
                function=match.group(1),
                filename=match.group(2),
                lineno=int(match.group(3)),
            )

        match = cls._FILE_PATTERN.match(raw)
        if match:
            return cls(
                function=match.group(1),
                filename=match.group(2),
            )

        return cls(function=raw)

    @property
    def location(self) -> str:
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


@dataclass(frozen=True)
class ModuleMapping:
    start: int
    end: int
    offset: int
    path: str

    @classmethod
    def parse(cls, line: str) -> Optional["ModuleMapping"]:
        parts = line.strip().split(maxsplit=5)
        if len(parts) < 6:
            return None
        addr_range, perms, offset, _dev, _inode, path = parts
        if "x" not in perms or path.startswith("["):
            return None
        try:
            start_s, end_s = addr_range.split("-", 1)
            return cls(
                start=int(start_s, 16),
                end=int(end_s, 16),
                offset=int(offset, 16),
                path=path,
            )
        except ValueError:
            return None

    def contains(self, address: int) -> bool:
        return self.start <= address < self.end

    def relative_address(self, address: int) -> int:
        return address - self.start + self.offset


@dataclass
class StackTrace:
    frames: tuple[Frame, ...]
    count: int

    @classmethod
    def parse(cls, line: str) -> StackTrace | None:
        line = line.strip()
        if not line or line.startswith('#'):
            return None

        parts = line.rsplit(' ', 1)
        if len(parts) != 2:
            return None

        try:
            count = int(parts[1])
        except ValueError:
            return None

        frames = tuple(Frame.parse(f) for f in parts[0].split(';'))
        return cls(frames=frames, count=count)

    def __str__(self) -> str:
        return ' -> '.join(str(f) for f in self.frames)


@dataclass
class FunctionStats:
    function: str
    filename: Optional[str]
    lineno: Optional[int]
    self_samples: int = 0
    total_samples: int = 0
    callers: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    callees: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def location(self) -> str:
        if self.filename and self.lineno:
            return f"{self.filename}:{self.lineno}"
        if self.filename:
            return self.filename
        return self.function


class FoldedStacksProfile:
    def __init__(self, stacks: list[StackTrace] | None = None):
        self.stacks: list[StackTrace] = stacks or []
        self._function_stats: dict[str, FunctionStats] | None = None
        self._module_mappings: tuple[ModuleMapping, ...] = ()

    @classmethod
    def load(cls, filepath: str | Path) -> FoldedStacksProfile:
        stacks = []
        with open(filepath) as f:
            for line in f:
                stack = StackTrace.parse(line)
                if stack:
                    stacks.append(stack)
        return cls(stacks)

    def with_module_mappings(
        self,
        mappings: list[ModuleMapping] | tuple[ModuleMapping, ...],
    ) -> FoldedStacksProfile:
        self._module_mappings = tuple(mappings)
        return self

    @property
    def total_samples(self) -> int:
        return sum(s.count for s in self.stacks)

    @staticmethod
    def _frame_matches(
        frame: Frame,
        function_name: str,
        filename_substring: Optional[str] = None,
    ) -> bool:
        if frame.function != function_name:
            return False
        if filename_substring is None:
            return True
        return frame.filename is not None and filename_substring in frame.filename

    @staticmethod
    def _looks_like_native_address(frame: Frame) -> bool:
        return bool(
            frame.filename
            and frame.function.startswith("0x")
            and ".so" in frame.filename
        )

    @staticmethod
    def _module_match(module_name: str, mapping_path: str) -> bool:
        return (
            mapping_path.endswith(module_name)
            or os.path.basename(mapping_path) == os.path.basename(module_name)
        )

    @staticmethod
    @lru_cache(maxsize=8192)
    def _resolve_address(module_path: str, relative_address: int) -> tuple[Optional[str], Optional[str], Optional[int]]:
        result = subprocess.run(
            ["addr2line", "-Cfie", module_path, hex(relative_address)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None, None, None

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) < 2:
            return None, None, None

        function = lines[0]
        location = lines[1]
        if function in {"??", "???"} or location in {"??:0", "??:?"}:
            return None, None, None

        if ":" in location:
            filename, lineno = location.rsplit(":", 1)
            try:
                return function, filename, int(lineno)
            except ValueError:
                return function, filename, None
        return function, location, None

    @staticmethod
    @lru_cache(maxsize=256)
    def _load_symbol_table(module_path: str) -> tuple[tuple[int, str], ...]:
        result = subprocess.run(
            ["nm", "-anC", "--defined-only", module_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ()

        symbols: list[tuple[int, str]] = []
        for line in result.stdout.splitlines():
            parts = line.strip().split(maxsplit=2)
            if len(parts) < 3:
                continue

            address_s, _symbol_type, name = parts
            if address_s in {"U", "w", "v"}:
                continue

            try:
                address = int(address_s, 16)
            except ValueError:
                continue

            if name:
                symbols.append((address, name))

        return tuple(symbols)

    @classmethod
    @lru_cache(maxsize=8192)
    def _resolve_symbol_name(cls, module_path: str, relative_address: int) -> Optional[str]:
        symbols = cls._load_symbol_table(module_path)
        if not symbols:
            return None

        addresses = [address for address, _name in symbols]
        idx = bisect_right(addresses, relative_address) - 1
        if idx < 0:
            return None
        return symbols[idx][1]

    def symbolize_native_frames(self) -> FoldedStacksProfile:
        if not self._module_mappings:
            return self

        symbolized_stacks: list[StackTrace] = []
        for stack in self.stacks:
            symbolized_frames = []
            for frame in stack.frames:
                if not self._looks_like_native_address(frame):
                    symbolized_frames.append(frame)
                    continue

                try:
                    absolute_address = int(frame.function, 16)
                except ValueError:
                    symbolized_frames.append(frame)
                    continue

                resolved_frame = frame
                for mapping in self._module_mappings:
                    if not frame.filename or not self._module_match(frame.filename, mapping.path):
                        continue
                    if not mapping.contains(absolute_address):
                        continue

                    relative_address = mapping.relative_address(absolute_address)
                    function, filename, lineno = self._resolve_address(mapping.path, relative_address)
                    if function:
                        resolved_frame = Frame(
                            function=function,
                            filename=filename or mapping.path,
                            lineno=lineno,
                        )
                    else:
                        function = self._resolve_symbol_name(mapping.path, relative_address)
                        if function:
                            resolved_frame = Frame(
                                function=function,
                                filename=mapping.path,
                            )
                    break

                symbolized_frames.append(resolved_frame)

            symbolized_stacks.append(StackTrace(frames=tuple(symbolized_frames), count=stack.count))

        return FoldedStacksProfile(symbolized_stacks).with_module_mappings(self._module_mappings)

    def _build_function_stats(self) -> dict[str, FunctionStats]:
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

                if i == len(stack.frames) - 1:
                    stats[key].self_samples += stack.count

                if key not in seen_in_stack:
                    stats[key].total_samples += stack.count
                    seen_in_stack.add(key)

                if i > 0:
                    caller = str(stack.frames[i - 1])
                    stats[key].callers[caller] += stack.count

                if i < len(stack.frames) - 1:
                    callee = str(stack.frames[i + 1])
                    stats[key].callees[callee] += stack.count

        return stats

    @property
    def function_stats(self) -> dict[str, FunctionStats]:
        if self._function_stats is None:
            self._function_stats = self._build_function_stats()
        return self._function_stats

    def hottest_functions(self, n: int = 10, by: str = "self") -> list[FunctionStats]:
        key_fn = (
            (lambda s: s.self_samples)
            if by == "self"
            else (lambda s: s.total_samples)
        )
        sorted_stats = sorted(
            self.function_stats.values(),
            key=key_fn,
            reverse=True,
        )
        return sorted_stats[:n]

    def filter_under_function(
        self,
        function_name: str,
        filename_substring: Optional[str] = None,
    ) -> FoldedStacksProfile:
        filtered = []
        for stack in self.stacks:
            target_idx = None
            for i, frame in enumerate(stack.frames):
                if self._frame_matches(frame, function_name, filename_substring):
                    target_idx = i
                    break

            if target_idx is not None:
                trimmed_frames = stack.frames[target_idx:]
                filtered.append(StackTrace(frames=trimmed_frames, count=stack.count))

        return FoldedStacksProfile(filtered).with_module_mappings(self._module_mappings)

    def exclude_under_function(
        self,
        function_name: str,
        filename_substring: Optional[str] = None,
    ) -> FoldedStacksProfile:
        filtered = []
        for stack in self.stacks:
            if any(
                self._frame_matches(frame, function_name, filename_substring)
                for frame in stack.frames
            ):
                continue
            filtered.append(stack)
        return FoldedStacksProfile(filtered).with_module_mappings(self._module_mappings)

    def report(self, n: int = 5) -> str:
        lines = []
        total = self.total_samples

        unresolved_native = sum(
            1
            for stack in self.stacks
            for frame in stack.frames
            if self._looks_like_native_address(frame)
        )
        if unresolved_native:
            lines.append(
                f"Native symbolization note: {unresolved_native} native address frames remain unresolved."
            )
            lines.append("")

        lines.append("Top hotspots by self time (where CPU is actually spending time)")
        lines.append("")
        lines.append(f"{'% time':>6}  {'Function':<30}  Location")
        lines.append(f"{'-'*6}  {'-'*30}  {'-'*40}")

        for stats in self.hottest_functions(n, by="self"):
            self_pct = 100 * stats.self_samples / total if total else 0
            lines.append(f"{self_pct:>6.1f}%  {stats.function:<30}  {stats.location}")

        lines.append("")
        lines.append("")
        lines.append("Top functions by total time (including calls to other functions)")
        lines.append("")
        lines.append(f"{'% time':>6}  {'Function':<30}  Location")
        lines.append(f"{'-'*6}  {'-'*30}  {'-'*40}")

        for stats in self.hottest_functions(n + 1, by="total"):
            if stats.function == "experiment":
                continue
            total_pct = 100 * stats.total_samples / total if total else 0
            lines.append(f"{total_pct:>6.1f}%  {stats.function:<30}  {stats.location}")

        return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze py-spy folded stacks.")
    parser.add_argument("profile", help="Path to folded stacks profile.")
    parser.add_argument(
        "--under",
        default="experiment",
        help="Keep only stacks under this function. Use an empty string to skip.",
    )
    parser.add_argument(
        "--exclude-under",
        action="append",
        default=[],
        help="Drop any stack that contains this function. Can be repeated.",
    )
    parser.add_argument(
        "--filename-substring",
        help="Only match frames whose filename contains this substring.",
    )
    parser.add_argument(
        "--maps",
        help="Saved /proc/<pid>/maps snapshot captured during profiling.",
    )
    args = parser.parse_args()

    profile = FoldedStacksProfile.load(args.profile)
    if args.maps:
        mappings = []
        with open(args.maps) as f:
            for line in f:
                mapping = ModuleMapping.parse(line)
                if mapping:
                    mappings.append(mapping)
        profile = profile.with_module_mappings(mappings).symbolize_native_frames()

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
