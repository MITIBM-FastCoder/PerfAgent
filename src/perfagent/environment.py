"""Docker environment used by PerfAgent.

Extends mini-swe-agent's `DockerEnvironment` to allow command prefix applied to every executed
command (GSO needs this to automatically activate the testbed venv), and a `docker cp` helper
for copying harness files into the container.
"""

import subprocess
from pathlib import Path
from typing import Any

from minisweagent.environments.docker import DockerEnvironment, DockerEnvironmentConfig


class PerfDockerEnvironmentConfig(DockerEnvironmentConfig):
    command_prefix: str = ""
    """Command prepended to every executed command, joined with `&&`. If it empty, then no prefix is added."""


class PerfDockerEnvironment(DockerEnvironment):
    def __init__(self, *, config_class: type = PerfDockerEnvironmentConfig, **kwargs):
        super().__init__(config_class=config_class, **kwargs)

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        """Execute a command in the container with `command_prefix`."""
        if self.config.command_prefix:
            action = {**action, "command": f"{self.config.command_prefix} && {action.get('command', '')}"}
        return super().execute(action, cwd, timeout=timeout)

    def copy_to_container(self, src: str | Path, dest: str) -> None:
        """Copy a host file or directory into the container with `docker cp`."""
        assert self.container_id, "Container not started"
        result = subprocess.run(
            [self.config.executable, "cp", str(src), f"{self.container_id}:{dest}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            raise RuntimeError(f"docker cp {src} -> {dest} failed: {details}")
        self.logger.debug(f"copied {src} to {self.container_id}:{dest}")
