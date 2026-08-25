
from dataclasses import dataclass, field
from pathlib import Path

# py-spy --native needs SYS_PTRACE; chattr +i on the harness scripts needs LINUX_IMMUTABLE.
UNIFORM_RUN_ARGS = [
    "--rm",
    "--cap-add=SYS_PTRACE",
    "--cap-add=LINUX_IMMUTABLE",
    "--security-opt=seccomp=unconfined",
]

@dataclass
class ContainerFile:
    src: Path
    dest: str
    immutable: bool = False  # chattr +i after copy to docker container to ensure agent cannot modify it, used for build, test, and profiling scripts
    executable: bool = False  # chmod +x after copy to docker container

@dataclass
class SetupCommand:
    command: str
    cwd: str = "/"
    context: str = ""

@dataclass
class HarnessSpec:
    instance_id: str
    repo: str
    image: str  # full image name, e.g. "ryandeng1/perfagent:gso.<instance_id>"
    build_script: str
    test_script: str
    files: list[ContainerFile] = field(default_factory=list)
    stable_suite_tar: Path | None = None
    testmon_seed: Path | None = None
    pre_build: bool = False  # run the build script during setup, used for llama/tokenizers repo in GSO to allow py-spy to see rust symbols
    setup_commands: list[SetupCommand] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    forward_env: list[str] = field(default_factory=lambda: ["HF_TOKEN"])
    run_args: list[str] = field(default_factory=lambda: list(UNIFORM_RUN_ARGS))
    command_prefix: str = ""
    exec_timeout: int = 7200
    build_script_path: str = "/build.sh"
    test_script_path: str = "/run_tests.sh"
    workload_script_path: str = "/perf_script.py"
    profile_command: str = "python /profile_prob_script.py"
    reference_profile_command: str = "python /profile_prob_script.py --reference"
    agent_run_kwargs: dict = field(default_factory=dict)
