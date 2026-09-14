"""
Rust-aware extension of parse_pyspy_enhanced for repos with native Rust extensions.

Handles repos like huggingface/tokenizers where the hot code is compiled Rust
inside a .so file.  Demangling Rust symbols, mapping them to .rs source files,
and treating repo-crate functions as repo code so that hotspots / files /
modules are populated instead of being empty.
"""

from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from pathlib import Path

from parse_pyspy_enhanced import (
    REPO_ROOT_PATH,
    FoldedStacksProfile,
    Frame,
    FunctionStats,
    StackTrace,
    _normalize_repo_filename,
    _repo_source_file_set,
    _repo_source_files,
)

# ---------------------------------------------------------------------------
# Rust demangling
# ---------------------------------------------------------------------------

_RUST_DEMANGLE_MAP = (
    ("$LT$", "<"),
    ("$GT$", ">"),
    ("$RF$", "&"),
    ("$u20$", " "),
    ("$u7b$", "{"),
    ("$u7d$", "}"),
    ("$LP$", "("),
    ("$RP$", ")"),
    ("$C$", ","),
    ("..", "::"),
)

_HASH_SUFFIX_RE = re.compile(r"::h[0-9a-f]{16}$")
_IMPL_RE = re.compile(r"<([^>]+?)\s+as\s+([^>]+)>::(.+)")


def _demangle_rust(name: str) -> str:
    """Best-effort Rust symbol demangling."""
    if name.startswith("_$"):
        name = name[1:]
    for pattern, replacement in _RUST_DEMANGLE_MAP:
        name = name.replace(pattern, replacement)
    if _HASH_SUFFIX_RE.search(name):
        name = name.rsplit("::", 1)[0]
    return name


# ---------------------------------------------------------------------------
# Repo-native .so detection
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _repo_native_crate_names() -> frozenset[str]:
    """Detect Rust crate names for native extensions built from the repo."""
    crate_names: set[str] = set()
    try:
        for entry in REPO_ROOT_PATH.iterdir():
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            if (entry / "Cargo.toml").exists():
                crate_names.add(entry.name)
                continue
            if any(entry.rglob("*.rs")):
                crate_names.add(entry.name)
    except OSError:
        pass
    # bindings/python/Cargo.toml pattern (tokenizers uses this)
    try:
        cargo_path = REPO_ROOT_PATH / "bindings" / "python" / "Cargo.toml"
        if cargo_path.exists():
            m = re.search(
                r'^name\s*=\s*"([^"]+)"',
                cargo_path.read_text(),
                re.MULTILINE,
            )
            if m:
                crate_names.add(m.group(1).replace("-", "_"))
    except Exception:
        pass
    return frozenset(crate_names)


def _so_package_name(filename: str) -> str | None:
    """``tokenizers/tokenizers.cpython-39-…-linux-gnu.so`` → ``tokenizers``."""
    if not filename or not filename.endswith(".so"):
        return None
    parts = filename.rsplit("/", 1)
    if len(parts) == 2:
        return parts[0].split("/")[-1]
    base = parts[0]
    if ".cpython-" in base:
        return base.split(".cpython-")[0]
    return None


@lru_cache(maxsize=None)
def _is_repo_native_so(filename: str | None) -> bool:
    pkg = _so_package_name(filename)
    return pkg is not None and pkg in _repo_native_crate_names()


# ---------------------------------------------------------------------------
# Rust crate path → .rs source file mapping
# ---------------------------------------------------------------------------

def _rust_crate_path_to_source(
    crate_path_segments: list[str], filename_hint: str | None = None
) -> str | None:
    """Map Rust module segments (after crate name) to a ``.rs`` source file.

    The core crate and the Python bindings crate are both ``tokenizers`` in symbol names, so a
    path can match a file in either. When py-spy reported a source basename for the frame
    (``filename_hint``), the candidate with that basename wins; otherwise the first match does.
    """
    repo_files = _repo_source_file_set()
    crate_names = _repo_native_crate_names()

    roots: list[str] = [f"{cn}/src" for cn in sorted(crate_names)]
    roots.append("bindings/python/src")

    candidates: list[str] = []
    for root in roots:
        for i in range(len(crate_path_segments), 0, -1):
            seg = crate_path_segments[:i]
            for candidate in (
                f"{root}/{'/'.join(seg)}.rs",
                f"{root}/{'/'.join(seg)}/mod.rs",
            ):
                if candidate in repo_files and candidate not in candidates:
                    candidates.append(candidate)
    if not candidates:
        return None
    if filename_hint:
        basename = filename_hint.rsplit("/", 1)[-1]
        for candidate in candidates:
            if candidate.rsplit("/", 1)[-1] == basename:
                return candidate
    return candidates[0]


def _resolve_frame(frame: Frame, crate_names: frozenset[str]) -> Frame:
    """Resolve a single frame from a repo native .so into a clean Frame."""
    demangled = _demangle_rust(frame.function)

    # Handle trait impl: <Type as Trait>::method
    impl_match = _IMPL_RE.match(demangled)
    if impl_match:
        impl_type = impl_match.group(1)
        method = impl_match.group(3)
        impl_parts = impl_type.split("::")
        if impl_parts[0] in crate_names:
            source = _rust_crate_path_to_source(impl_parts[1:], frame.filename)
            type_name = impl_parts[-1] if impl_parts else impl_type
            return Frame(
                function=f"{type_name}::{method}",
                filename=source or frame.filename,
                lineno=frame.lineno,
            )
        return frame

    # Handle direct crate path: tokenizers::normalizers::foo
    parts = demangled.split("::") if "::" in demangled else []
    first_seg = parts[0] if parts else ""
    if first_seg not in crate_names:
        return frame

    source = _rust_crate_path_to_source(parts[1:], frame.filename)
    if len(parts) >= 3:
        clean_fn = "::".join(parts[-2:])
    elif len(parts) == 2:
        clean_fn = parts[1]
    else:
        clean_fn = demangled

    return Frame(function=clean_fn, filename=source or frame.filename, lineno=frame.lineno)


# ---------------------------------------------------------------------------
# Subclass with Rust-aware overrides
# ---------------------------------------------------------------------------

class RustAwareFoldedStacksProfile(FoldedStacksProfile):
    """FoldedStacksProfile with Rust native extension awareness."""

    @classmethod
    def load(cls, filepath: str | Path) -> RustAwareFoldedStacksProfile:
        stacks = []
        with open(filepath) as f:
            for line in f:
                stack = StackTrace.parse(line)
                if stack:
                    stacks.append(stack)
        return cls(stacks)

    def filter_under_function(self, function_name: str) -> RustAwareFoldedStacksProfile:
        filtered = []
        for stack in self.stacks:
            for i, frame in enumerate(stack.frames):
                if frame.function == function_name:
                    filtered.append(StackTrace(frames=stack.frames[i:], count=stack.count))
                    break
        return RustAwareFoldedStacksProfile(filtered)

    def exclude_under_function(self, function_name: str) -> RustAwareFoldedStacksProfile:
        filtered = [s for s in self.stacks if not any(f.function == function_name for f in s.frames)]
        return RustAwareFoldedStacksProfile(filtered)

    def resolve_native_repo_frames(self) -> RustAwareFoldedStacksProfile:
        """Rewrite frames from the repo's native code.

        * Demangles Rust symbols.
        * Resolves repo-crate functions to .rs source files, both for frames py-spy could only
          attribute to the .so and for frames it symbolized to a bare source basename.
        * Leaves dependency crate frames (alloc, core, pyo3, …) unchanged.
        """
        crate_names = _repo_native_crate_names()
        if not crate_names:
            return self

        resolved: list[StackTrace] = []
        for stack in self.stacks:
            new_frames: list[Frame] = []
            for frame in stack.frames:
                filename = frame.filename or ""
                if filename.endswith(".so") and _is_repo_native_so(filename):
                    new_frames.append(_resolve_frame(frame, crate_names))
                elif filename.endswith(".rs"):
                    # py-spy symbolized the frame from debug info and reports only the source
                    # basename. Resolve it through the crate path so bindings/python/src/encoding.rs
                    # is not lost among the other encoding.rs files in the repo; frames from other
                    # crates (pyo3, core, std) come back unchanged.
                    new_frames.append(_resolve_frame(frame, crate_names))
                else:
                    new_frames.append(frame)
            resolved.append(StackTrace(frames=tuple(new_frames), count=stack.count))

        return RustAwareFoldedStacksProfile(resolved)

    # -- repo-code predicates that understand native .so -------------------

    @staticmethod
    def _is_repo_code(filename: str | None) -> bool:
        if not filename:
            return False
        path = _normalize_repo_filename(filename)
        if not path:
            return False
        if path.endswith(".so"):
            return _is_repo_native_so(path)
        if path.startswith("/") or path.startswith(".venv/"):
            return False
        return path in _repo_source_file_set()

    @staticmethod
    def _is_repo_frame_name(name: str) -> bool:
        frame = Frame.parse(name)
        if RustAwareFoldedStacksProfile._is_repo_code(frame.filename):
            return True
        if (
            frame.filename
            and frame.filename.endswith(".so")
            and _is_repo_native_so(frame.filename)
        ):
            demangled = _demangle_rust(frame.function)
            first = demangled.split("::")[0] if "::" in demangled else ""
            if first in _repo_native_crate_names():
                return True
            impl_match = _IMPL_RE.match(demangled)
            if impl_match:
                return impl_match.group(1).split("::")[0] in _repo_native_crate_names()
        return False

    @staticmethod
    def _module_from_filename(filename: str | None, function: str | None = None) -> str:
        if not filename:
            return "<unknown>"
        path = _normalize_repo_filename(filename)
        if not path:
            return "<unknown>"
        if path.endswith(".so"):
            if function and _is_repo_native_so(path):
                demangled = _demangle_rust(function)
                if "::" in demangled:
                    parts = demangled.split("::")
                    if parts[0] in _repo_native_crate_names():
                        depth = min(3, len(parts) - 1)
                        return "::".join(parts[: max(2, depth)])
            base = path.rsplit("/", 1)[-1]
            if ".cpython-" in base:
                base = base.split(".cpython-")[0] + ".so"
            return base
        path = path.lstrip("./").lstrip("/")
        if path.endswith(".py"):
            path = path[:-3]
        if path.endswith("/__init__"):
            path = path[:-9]
        return path.replace("/", ".") if path else "<unknown>"

    # Override aggregation methods to pass function names through

    def module_stats(self) -> dict[str, dict[str, int]]:
        return self._aggregate_by_key(
            lambda s: self._module_from_filename(s.filename, s.function)
        )

    def repo_module_stats(self) -> dict[str, dict[str, int]]:
        return self._aggregate_by_key(
            lambda s: self._module_from_filename(s.filename, s.function)
            if self._is_repo_code(s.filename)
            else None
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze py-spy folded stacks (Rust-aware)."
    )
    parser.add_argument("profile", help="Path to folded stacks profile.")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--top-stacks", type=int, default=5)
    parser.add_argument("--top-callers", type=int, default=3)
    parser.add_argument("--top-callees", type=int, default=3)
    parser.add_argument("--top-files", type=int, default=3)
    parser.add_argument("--top-modules", type=int, default=5)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    profile = RustAwareFoldedStacksProfile.load(args.profile)
    profile = profile.resolve_native_repo_frames()
    # Everything under experiment() is measured time, including a setup() the workload calls from
    # inside it, so nothing below experiment() is excluded.
    profile = profile.filter_under_function("experiment")

    report = profile.to_json(
        top_n=args.top,
        top_stacks_n=args.top_stacks,
        top_callers_n=args.top_callers,
        top_callees_n=args.top_callees,
        top_files_n=args.top_files,
        top_modules_n=args.top_modules,
    )
    print(json.dumps(report, indent=2))
