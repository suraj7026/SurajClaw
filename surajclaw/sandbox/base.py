"""Sandbox backend interfaces."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    code: int

    @property
    def ok(self) -> bool:
        return self.code == 0


class SandboxBackendHandle:
    """Active sandbox runtime capable of shell execution."""

    id: str
    workdir: str

    def run_shell_command(
        self,
        script: str,
        timeout_seconds: int | None = None,
        session_id: str | None = None,
    ) -> SandboxResult:
        raise NotImplementedError
