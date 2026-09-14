"""Builds perfagent's patched py-spy inside each task container and puts it first on PATH.

Why a patch: the task images run Python 3.8-3.10, where py-spy has to guess each thread's kernel
id from a CPU register when `--native` is on. On thread-heavy workloads (rayon, tokio, pyarrow)
that guess misses, and py-spy then drops the whole sample with "failed to get os threadid". Three
GSO tasks lost ~93% of their samples this way and used to be pinned to a Python-only profile. The
patch (assets/pyspy/*.patch, against py-spy 0.4.2) reads the id from glibc's thread struct instead,
and keeps a thread's Python frames when its native frames cannot be merged.

Why build in the container: the executable must link against the image's own libunwind, and every
task image carries the Rust toolchain that installed its stock py-spy. The build downloads the
py-spy crate and its dependencies from crates.io and takes a minute or two per container.
"""

from pathlib import Path

from perfagent.environment import PerfDockerEnvironment

PYSPY_VERSION = "0.4.2"
ASSETS = Path(__file__).parent / "assets" / "pyspy"
PATCH = ASSETS / f"py-spy-{PYSPY_VERSION}-perfagent.patch"
BUILD_SCRIPT = ASSETS / "build_pyspy.sh"
CONTAINER_PATH = "/usr/local/bin/py-spy"
BUILD_DIR = "/tmp/perfagent-pyspy-build"
BUILD_TIMEOUT = 1800


def install(env: PerfDockerEnvironment) -> None:
    """Build the patched py-spy in the container and make it the `py-spy` the profiler scripts find on PATH."""
    _execute_or_raise(env, f"mkdir -p {BUILD_DIR}", context="create py-spy build dir")
    env.copy_to_container(src=PATCH, dest=f"{BUILD_DIR}/py-spy.patch")
    env.copy_to_container(src=BUILD_SCRIPT, dest=f"{BUILD_DIR}/build_pyspy.sh")
    _execute_or_raise(
        env,
        f"bash {BUILD_DIR}/build_pyspy.sh {PYSPY_VERSION} {BUILD_DIR} {CONTAINER_PATH}",
        context="build patched py-spy",
        timeout=BUILD_TIMEOUT,
    )
    # The images list their own py-spy earlier on PATH (/root/.cargo/bin); point that name at ours.
    _execute_or_raise(
        env,
        f'p="$(command -v py-spy || true)"; if [ -n "$p" ] && [ "$p" != {CONTAINER_PATH} ]; then ln -sf {CONTAINER_PATH} "$p"; fi',
        context="link py-spy onto PATH",
    )
    output = _execute_or_raise(env, "py-spy --version", context="check py-spy")["output"]
    if PYSPY_VERSION not in output:
        raise RuntimeError(f"py-spy on PATH is not the {PYSPY_VERSION} build just installed: {output.strip()!r}")


def _execute_or_raise(env: PerfDockerEnvironment, command: str, *, context: str, timeout: int | None = None) -> dict:
    output = env.execute({"command": command}, timeout=timeout)
    if output["returncode"] != 0:
        raise RuntimeError(f"{context} failed. output: {output['output']}")
    return output
