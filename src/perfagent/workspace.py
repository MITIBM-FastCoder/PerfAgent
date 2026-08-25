"""Sets up the docker container for a benchmark task"""

import shlex
import tempfile

import docker
from rich.console import Console

from minisweagent.environments.docker import DockerEnvironment

from perfagent.spec import HarnessSpec

console = Console(highlight=False)

def _execute_or_raise(env: DockerEnvironment, command: str, *, cwd: str = "", context: str) -> dict:
    output = env.execute({"command": command}, cwd=cwd)
    assert output["returncode"] == 0, f"{context} failed. output: {output['output']}"
    return output

def _copy_script(env: DockerEnvironment, text: str, dest: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=True) as f:
        f.write(text)
        f.flush()
        env.copy_to_container(src=f.name, dest=dest)
    _execute_or_raise(env, f"chmod +x {shlex.quote(dest)}", context=f"chmod {dest}")
    _execute_or_raise(env, f"chattr +i {shlex.quote(dest)}", context=f"chattr {dest}")

def materialize(spec: HarnessSpec, environment_config: dict | None = None) -> DockerEnvironment:
    environment_config = dict(environment_config or {})
    docker.from_env().images.pull(spec.image)  # anonymous pull from the public DockerHub mirror
    console.print(f"image: {spec.image}", style="bright_cyan")

    yaml_env = environment_config.pop("env", {})
    timeout = environment_config.pop("timeout", spec.exec_timeout)
    if environment_config:
        raise ValueError(f"unknown environment config keys: {sorted(environment_config)}")

    env = DockerEnvironment(
        image=spec.image,
        forward_env=list(spec.forward_env),
        command_prefix=spec.command_prefix,
        run_args=list(spec.run_args),
        timeout=timeout,
        env={**yaml_env, **spec.env},
    )

    for file in spec.files:
        env.copy_to_container(src=str(file.src), dest=file.dest)
        if file.executable:
            _execute_or_raise(env, f"chmod +x {shlex.quote(file.dest)}", context=f"chmod {file.dest}")

    console.print("--- build script ---", style="bright_cyan")
    console.print(spec.build_script)
    _copy_script(env, spec.build_script, spec.build_script_path)

    if spec.pre_build:
        console.print(
            f"prebuilding {spec.repo} before initial profiling to ensure symbolized native stacks",
            style="bright_cyan",
        )
        prebuild_output = env.execute({"command": spec.build_script_path}, cwd="/")
        if prebuild_output["returncode"] != 0:
            raise RuntimeError(f"prebuild failed for {spec.instance_id}: {prebuild_output['output']}")
        console.print(prebuild_output["output"], style="bright_blue")

    for cmd in spec.setup_commands:
        _execute_or_raise(env, cmd.command, cwd=cmd.cwd, context=cmd.context or cmd.command)

    console.print("--- run tests script ---", style="bright_cyan")
    console.print(spec.test_script)
    _copy_script(env, spec.test_script, spec.test_script_path)

    if spec.stable_suite_tar is not None:
        env.copy_to_container(src=str(spec.stable_suite_tar), dest="/stable_suite.tar.gz")
        _execute_or_raise(env, "tar -xzf /stable_suite.tar.gz -C /", context="extract stable suite")
        _execute_or_raise(env, "chattr -R +i /stable_suite", context="chattr stable suite")

    if spec.testmon_seed is not None:
        env.copy_to_container(src=str(spec.testmon_seed), dest="/.testmondata")
        _execute_or_raise(env, "chmod u+rw /.testmondata", context="chmod /.testmondata")

    for file in spec.files:
        if file.immutable:
            _execute_or_raise(env, f"chattr +i {shlex.quote(file.dest)}", context=f"chattr {file.dest}")

    return env
