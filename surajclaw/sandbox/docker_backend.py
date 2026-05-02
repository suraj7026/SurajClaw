"""Docker sandbox backend."""
from __future__ import annotations

import subprocess
import re

from django.conf import settings

from sandbox.base import SandboxBackendHandle, SandboxResult
from sandbox.policies import validate_command


class DockerSandboxBackend(SandboxBackendHandle):
    id = "docker"
    workdir = "/workspace"

    def run_shell_command(
        self,
        script: str,
        timeout_seconds: int | None = None,
        session_id: str | None = None,
    ) -> SandboxResult:
        ok, why = validate_command(script)
        if not ok:
            return SandboxResult(stdout="", stderr=why, code=126)
        timeout = timeout_seconds or settings.SANDBOX_TIMEOUT_SECONDS
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            settings.SANDBOX_MEMORY_LIMIT,
            "--cpus",
            str(settings.SANDBOX_CPU_LIMIT),
            "-w",
            self.workdir,
            *self._workspace_mount_args(session_id),
            settings.SANDBOX_IMAGE,
            "sh",
            "-lc",
            script,
        ]
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(stdout=exc.stdout or "", stderr=f"timeout: {exc}", code=124)
        except OSError as exc:
            return SandboxResult(stdout="", stderr=f"docker unavailable: {exc}", code=127)
        return SandboxResult(stdout=proc.stdout, stderr=proc.stderr, code=proc.returncode)

    def _workspace_mount_args(self, session_id: str | None) -> list[str]:
        if str(settings.SANDBOX_SCOPE).lower() == "ephemeral":
            return []
        access = str(settings.SANDBOX_WORKSPACE_ACCESS).lower()
        if access in {"none", "off", "false"}:
            return []
        mode = "ro" if access in {"read_only", "readonly", "ro"} else "rw"
        volume = _workspace_volume_name(session_id or "default")
        return ["-v", f"{volume}:{self.workdir}:{mode}"]


def get_sandbox_backend() -> SandboxBackendHandle:
    if settings.SANDBOX_BACKEND != "docker":
        raise ValueError(f"unsupported sandbox backend: {settings.SANDBOX_BACKEND}")
    return DockerSandboxBackend()


def cleanup_session_workspace(session_id: str) -> None:
    subprocess.run(
        ["docker", "volume", "rm", _workspace_volume_name(session_id)],
        capture_output=True,
        text=True,
        check=False,
    )


def _workspace_volume_name(session_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(session_id))[:80]
    return f"surajclaw_sandbox_{safe or 'default'}"
