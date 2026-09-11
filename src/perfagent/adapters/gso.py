"""GSO benchmark adapter."""

import re
from pathlib import Path

from perfagent import pytest_cmd
from perfagent import repo_config as rc
from perfagent.adapters.base import IMAGE_REPO, PACKAGED_ASSET_HINT, BenchmarkAdapter, Instance, require_artifact
from perfagent.spec import ContainerFile, HarnessSpec, SetupCommand

# For tasks in HEAVY_TIMING_REPOS, run the timing script only once, otherwise run the timing script 5 times, mirroring the GSO evaluation, to reduce variance.
HEAVY_TIMING_REPOS = ("llama-cpp-python", "onnxruntime", "tokenizers")

DEFAULT_PYTEST_TOOLING = [
    "pytest",
    "pytest-reportlog",
    "pytest-testmon",
    "pytest-timeout",
    "pytest-xdist",
    "pytest-randomly",
    "hypothesis",
]

# Patches for specific repos to enable running pytest.
TEST_RUN_PATCH_SPECS = [
    {
        "override_key": "patch_transformers_testing_utils",
        "script": "patch_transformers_testing_utils.py",
        "context": "patch transformers testing_utils",
        "args": ["--scope", "installed"],
    },
    {
        "override_key": "patch_pydantic_yield_fixture",
        "script": "patch_pydantic_yield_fixture.py",
        "context": "patch pydantic yield_fixture",
        "args": [],
    },
    {
        "override_key": "patch_pandas_skip_slow",
        "script": "patch_pandas_skip_slow.py",
        "context": "patch pandas skip_slow option",
        "args": ["--scope", "installed"],
    },
]

PROFILER_VARIANT_FILES = {
    "default": "profile_prob_script.py",
    "llama": "profile_prob_script_llama.py",
    "no_native": "profile_prob_script_no_native.py",
}
PARSER_VARIANT_FILES = {
    "default": "parse_pyspy_enhanced.py",
    "llama": "parse_pyspy_llama.py",
    "rust": "parse_pyspy_enhanced_rust.py",
}


# Modified build commands to ensure debug symbols are enabled for the profiler (py-spy).
def install_commands_debug(repo: str, install_commands: list[str]) -> list[str]:
    repo_url = f"https://github.com/{repo}"

    if "numpy" in repo_url:
        return [
            "uv venv --python 3.11",
            "source .venv/bin/activate",
            "which python",
            "python --version",
            "git submodule update --init",
            "(uv pip install . --config-settings=setup-args=\"-Dbuildtype=debugoptimized\" --reinstall) || (sed -Ei 's/Cython>=3\\.0(\\.[0-9]+)?(,<3\\.1)?/Cython>=3.0,<3.1/I' pyproject.toml && uv pip install . --config-settings=setup-args=\"-Dbuildtype=debugoptimized\" --reinstall) || (uv venv --python 3.10 && source .venv/bin/activate && uv pip install \"setuptools<=59.8.0\" \"cython<0.30\" && CFLAGS=\"-g -O2\" CXXFLAGS=\"-g -O2\" uv run python setup.py build_ext --inplace)",
            "uv pip install requests dill pillow",
            "uv pip show numpy",
        ]

    if "pandas" in repo_url:
        return [
            'sed -Ei \'s/"setuptools[^"]*"/"setuptools<82"/\' pyproject.toml',
            "uv venv --python 3.10",
            "source .venv/bin/activate",
            "which python",
            "python --version",
            "uv pip install . --config-settings=setup-args=\"-Dbuildtype=debugoptimized\" --reinstall",
            'uv pip install requests dill "numpy<2.0"',
            "uv pip show pandas",
        ]

    if "tokenizers" in repo_url:
        return [
            'curl https://sh.rustup.rs -sSf | sh -s -- -y && export PATH="$HOME/.cargo/bin:$PATH"',
            "uv venv --python 3.9",
            "source .venv/bin/activate",
            '. "$HOME/.cargo/env"',
            "which python",
            "python --version",
            'uv pip install "maturin>=1.0,<2.0"',
            'export RUSTFLAGS="-A invalid_reference_casting -C debuginfo=2 -C force-frame-pointers=yes"',
            "export CARGO_PROFILE_RELEASE_DEBUG=2",
            "export CARGO_PROFILE_RELEASE_STRIP=none",
            "export CARGO_PROFILE_RELEASE_SPLIT_DEBUGINFO=off",
            "uv pip install ./bindings/python --reinstall",
            "uv pip install requests dill datasets==3.5.0 tiktoken scikit-learn",
            "uv pip show tokenizers",
        ]

    if "llama-cpp-python" in repo_url:
        return [
            "git submodule update --init --recursive",
            "rm -rf _skbuild/ build/ dist/ *.egg-info .venv/ build-pyspy",
            "uv venv --python 3.8",
            "source .venv/bin/activate",
            "which python",
            "python --version",
            "uv pip install huggingface_hub hf_transfer scikit-build cmake ninja 'setuptools<82' wheel",
            'uv pip install "llama_cpp_python @ ." --reinstall',
            'export PKG_DIR="$(cd /tmp && python -c \'import pathlib, llama_cpp; print(pathlib.Path(llama_cpp.__file__).resolve().parent)\')"',
            'export SOURCE_PKG_DIR="/testbed/llama_cpp"',
            "uv pip install requests dill datasets tiktoken transformers",
            'cmake -S . -B build-pyspy -G Ninja -DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_C_FLAGS_RELWITHDEBINFO="-O2 -g -fno-omit-frame-pointer" -DCMAKE_CXX_FLAGS_RELWITHDEBINFO="-O2 -g -fno-omit-frame-pointer"',
            'cmake --build build-pyspy -j"$(nproc)"',
            'export LIBLLAMA_PATH="$(for p in build-pyspy/vendor/llama.cpp/libllama.so build-pyspy/vendor/llama.cpp/src/libllama.so; do if [ -f "$p" ]; then printf %s "$p"; break; fi; done)"',
            'test -n "$LIBLLAMA_PATH"',
            'cp -f "$LIBLLAMA_PATH" "$PKG_DIR/libllama.so"',
            'if [ -f build-pyspy/vendor/llama.cpp/examples/llava/libllava.so ]; then cp -f build-pyspy/vendor/llama.cpp/examples/llava/libllava.so "$PKG_DIR/libllava.so"; fi',
            'cp -f "$LIBLLAMA_PATH" "$SOURCE_PKG_DIR/libllama.so"',
            'if [ -f build-pyspy/vendor/llama.cpp/examples/llava/libllava.so ]; then cp -f build-pyspy/vendor/llama.cpp/examples/llava/libllava.so "$SOURCE_PKG_DIR/libllava.so"; fi',
            "uv pip show llama-cpp-python",
        ]

    return install_commands


def adjust_build_commands_for_llama(commands: list[str]) -> list[str]:
    adjusted: list[str] = []
    for command in commands:
        if "cmake -S . -B build-pyspy" in command:
            command = command.replace(
                "-DCMAKE_BUILD_TYPE=Debug",
                "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
            )
            command = re.sub(r'\s-DCMAKE_C_FLAGS_DEBUG="[^"]*"', "", command)
            command = re.sub(r'\s-DCMAKE_CXX_FLAGS_DEBUG="[^"]*"', "", command)
            if "-DCMAKE_C_FLAGS_RELWITHDEBINFO=" not in command:
                command += ' -DCMAKE_C_FLAGS_RELWITHDEBINFO="-O2 -g3 -fno-omit-frame-pointer"'
            if "-DCMAKE_CXX_FLAGS_RELWITHDEBINFO=" not in command:
                command += ' -DCMAKE_CXX_FLAGS_RELWITHDEBINFO="-O2 -g3 -fno-omit-frame-pointer"'
        adjusted.append(command)

    adjusted.extend(
        [
            'file "$LIBLLAMA_PATH"',
            'readelf -S "$LIBLLAMA_PATH" | grep -E "\\.debug|\\.symtab|\\.dynsym" || true',
            'nm -anC --defined-only "$LIBLLAMA_PATH" | sed -n "1,20p" || true',
        ]
    )
    return adjusted


def build_tokenizers_debug_commands() -> list[str]:
    """Build commands to rebuild the tokenizers Rust extension with debug line tables."""
    return [
        r"""python3 -c "
import re
cargo = open('bindings/python/Cargo.toml').read()
if '[profile.release]' not in cargo:
    cargo += '\n[profile.release]\ndebug = 1\nlto = \"fat\"\n'
elif re.search(r'(?m)^\s*debug\s*=', cargo):
    cargo = re.sub(r'(?m)^(\s*debug\s*=\s*).*', r'\g<1>1', cargo)
else:
    cargo = re.sub(r'\[profile\.release\]', '[profile.release]\ndebug = 1', cargo)
open('bindings/python/Cargo.toml', 'w').write(cargo)
" """,
        r"""python3 -c "
t = open('bindings/python/pyproject.toml').read()
if \"'version'\" not in t and '\"version\"' not in t:
    t = t.replace(\"dynamic = [\", \"dynamic = [\n    'version',\")
    open('bindings/python/pyproject.toml', 'w').write(t)
" """,
        'export RUSTFLAGS="-A invalid_reference_casting -C debuginfo=2 -C force-frame-pointers=yes"',
        "cd bindings/python && maturin develop --release",
    ]


def _active_patch_specs(config: dict, instance_id: str) -> list[dict]:
    return [
        spec
        for spec in TEST_RUN_PATCH_SPECS
        if instance_id in rc.override_list(config, str(spec["override_key"]))
    ]

def _patch_commands(config: dict, instance_id: str) -> list[str]:
    return [
        pytest_cmd.shell_join(["python3", f"/{spec['script']}", *spec["args"]])
        for spec in _active_patch_specs(config, instance_id)
    ]

def _test_install_commands(config: dict, repo: str, instance_id: str) -> list[str]:
    repo_cfg = rc.repo_cfg(config, repo)
    tooling = repo_cfg.get("pytest_tooling_packages", DEFAULT_PYTEST_TOOLING)
    commands = [pytest_cmd.shell_join(["uv", "pip", "install", *tooling])]
    for packages in repo_cfg.get("extra_test_installs") or []:
        commands.append(pytest_cmd.shell_join(["uv", "pip", "install", *packages]))
    for packages in rc.override_map(config, "extra_test_installs", instance_id, []):
        commands.append(pytest_cmd.shell_join(["uv", "pip", "install", *packages]))
    return commands

class GsoAdapter(BenchmarkAdapter):
    name = "gso"

    def build_spec(self, instance: Instance, *, test_db_root: Path) -> HarnessSpec:
        instance_id, repo = instance.instance_id, instance.repo
        config = rc.get_repo_config("gso")
        assets = rc.assets_root("gso")

        stable_suite_tar = require_artifact(
            test_db_root / instance_id / "stable_suite.tar.gz",
            instance_id=instance_id,
            what="stable suite artifact",
        )
        workload = require_artifact(
            assets / "workloads" / instance_id / "perf_script.py",
            instance_id=instance_id,
            what="workload script (packaged asset)",
            hint=PACKAGED_ASSET_HINT,
        )

        is_llama_cpp = "llama-cpp-python" in repo
        is_tokenizers = "tokenizers" in repo

        build_commands = list(install_commands_debug(repo, instance.raw["install_commands"]))
        if is_llama_cpp:
            build_commands = adjust_build_commands_for_llama(build_commands)
        if is_tokenizers:
            build_commands = build_tokenizers_debug_commands()
        # test_install_commands reinstall some packages as the build commands from the benchmark may uninstall them
        test_install_commands = _test_install_commands(config, repo, instance_id)
        patch_commands = _patch_commands(config, instance_id)
        build_script = "\n".join(
            ["#!/bin/bash", "set -euxo pipefail"]
            + ["cd /testbed"]
            + build_commands
            + test_install_commands
            + patch_commands
        )

        test_script = pytest_cmd.build_gso_run_tests_script(instance_id, repo, stable_suite_tar)

        repo_cfg = rc.repo_cfg(config, repo)
        profiler_variant = rc.override_map(
            config, "profiler_variant", instance_id, repo_cfg.get("profiler_variant", "default")
        )
        parser_variant = repo_cfg.get("parser_variant", "default")

        files = [
            ContainerFile(src=assets / "scripts" / spec["script"], dest=f"/{spec['script']}")
            for spec in _active_patch_specs(config, instance_id)
        ]
        files += [
            ContainerFile(src=assets / "scripts" / "deselect_plugin.py", dest="/deselect_plugin.py"),
            ContainerFile(src=assets / "scripts" / "test_stats_plugin.py", dest="/test_stats_plugin.py"),
            ContainerFile(src=workload, dest="/perf_script.py", immutable=True),
            ContainerFile(
                src=assets / "profiler" / PROFILER_VARIANT_FILES[profiler_variant],
                dest="/profile_prob_script.py",
                immutable=True,
            ),
            ContainerFile(
                src=assets / "profiler" / PARSER_VARIANT_FILES[parser_variant],
                dest="/parse_pyspy.py",
                immutable=True,
            ),
        ]
        if is_tokenizers:
            files += [
                ContainerFile(src=assets / "profiler" / "parse_pyspy_enhanced.py", dest="/parse_pyspy_enhanced.py"),
                ContainerFile(src=assets / "profiler" / "parse_pyspy.py", dest="/parse_pyspy_base.py"),
            ]

        setup_commands = [
            SetupCommand(command=cmd, cwd="/testbed", context=f"install test dependencies for {instance_id}")
            for cmd in test_install_commands
        ]
        setup_commands += [
            SetupCommand(command=cmd, cwd="/testbed", context=str(spec["context"]))
            for spec, cmd in zip(_active_patch_specs(config, instance_id), patch_commands)
        ]

        env = {
            "PYTHONPATH": "/",
            "PYTHONHASHSEED": "0",
            "GSO_TIMING_ITERS": "1" if any(r in repo for r in HEAVY_TIMING_REPOS) else "5",
            "TESTMON_DATAFILE": pytest_cmd.gso_testmon_data_path(config, repo),
        }

        return HarnessSpec(
            instance_id=instance_id,
            repo=repo,
            image=f"{IMAGE_REPO}:{self.image_tag(instance)}",
            build_script=build_script,
            test_script=test_script,
            files=files,
            stable_suite_tar=stable_suite_tar,
            pre_build=is_llama_cpp or is_tokenizers,
            setup_commands=setup_commands,
            env=env,
            command_prefix="source /testbed/.venv/bin/activate",
        )
