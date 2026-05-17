"""Spawn the official Gemini CLI inside a sandboxed Docker container.

Headless invocation per the official docs:

    gemini -p "$TASK_PROMPT" --output-format json --yolo --model "$MODEL"

We capture the JSON object to a file inside the container, then echo it
between sentinel markers so the streaming parser can pull it back out of
the mixed stdout/stderr line stream.

Auth: the container mounts your host ``~/.gemini`` directory (which the
official ``gemini`` CLI populates on first login) so the same Google
account that backs the SurajClaw chat agent powers the coding agent too.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
from pathlib import Path
from typing import Any

from agents.types import ToolDefinition
from tools.coding._runner import run_coding_container
from tools.registry import register_tool

logger = logging.getLogger(__name__)


GEMINI_CLI_IMAGE = os.environ.get("GEMINI_CLI_IMAGE", "surajclaw-gemini-cli:latest")
GEMINI_CLI_DEFAULT_MODEL = os.environ.get("GEMINI_CLI_MODEL", "gemini-2.5-pro")

# Host directory the official gemini-cli writes OAuth credentials to.
# Override via env if you've relocated it.
GEMINI_HOST_AUTH_DIR = os.environ.get(
    "GEMINI_HOST_AUTH_DIR", str(Path.home() / ".gemini")
)

_RESULT_START = "===GEMINI_RESULT_START==="
_RESULT_END = "===GEMINI_RESULT_END==="


def _extract_gemini_output(stdout_lines: list[str]) -> tuple[str, dict[str, Any]]:
    """Pull the Gemini JSON envelope out of streamed stdout."""
    try:
        start = stdout_lines.index(_RESULT_START)
        end = stdout_lines.index(_RESULT_END, start + 1)
    except ValueError:
        return "", {"gemini_parsed": False, "reason": "sentinels missing"}
    blob = "\n".join(stdout_lines[start + 1 : end]).strip()
    if not blob:
        return "", {"gemini_parsed": False, "reason": "empty payload"}
    try:
        envelope = json.loads(blob)
    except json.JSONDecodeError as exc:
        return blob[:1200], {"gemini_parsed": False, "reason": f"invalid json: {exc}"}
    response_text = envelope.get("response") or ""
    err = envelope.get("error") or {}
    return response_text, {
        "gemini_parsed": True,
        "gemini_stats": envelope.get("stats") or {},
        "gemini_error": err,
    }


def gemini_cli_run(
    repo: str,
    branch: str,
    task: str,
    base_branch: str = "main",
    model: str = "",
    include_all_files: bool = False,
    session_id: str = "",
) -> dict:
    """Run ``gemini -p ... --output-format json`` against ``repo``.

    Args:
        repo: ``owner/name`` form.
        branch: new branch name.
        task: natural-language instruction.
        base_branch: base branch for the PR (default ``main``).
        model: Gemini model id (defaults to ``GEMINI_CLI_MODEL`` env).
        include_all_files: pass ``--all-files`` so the CLI loads the whole
            repo into context. Cheap for small repos; expensive otherwise.
    """
    auth_dir = Path(GEMINI_HOST_AUTH_DIR)
    if not auth_dir.exists():
        return {
            "ok": False,
            "output": (
                f"Gemini OAuth credentials not found at {auth_dir}. "
                "Run `gemini auth login` on the host (or `npx @google/gemini-cli "
                "auth login`) to authenticate."
            ),
            "error": "missing_gemini_auth",
        }
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not gh_token:
        return {
            "ok": False,
            "output": "GH_TOKEN (or GITHUB_TOKEN) is required so gh CLI can push and open the PR",
            "error": "missing_env",
        }

    model_arg = (model or GEMINI_CLI_DEFAULT_MODEL).strip()

    # Bash fragment: run gemini headless, save JSON envelope to a file, echo
    # it between sentinels so the host-side parser can find it among the
    # rest of the streamed git / gh output.
    ai_command = "\n".join(
        [
            "GEMINI_OUT=/tmp/gemini-output.json",
            "set +e",  # gemini's non-zero exit shouldn't kill the whole script
            (
                "gemini --prompt \"$TASK_PROMPT\" "
                f"--model {shlex.quote(model_arg)} "
                "--output-format json --yolo "
                + ("--all-files " if include_all_files else "")
                + "> \"$GEMINI_OUT\""
            ),
            "GEMINI_RC=$?",
            "set -e",
            f"echo {shlex.quote(_RESULT_START)}",
            "cat \"$GEMINI_OUT\" || true",
            f"echo {shlex.quote(_RESULT_END)}",
            'echo "gemini exit code: $GEMINI_RC"',
        ]
    )

    return run_coding_container(
        image=GEMINI_CLI_IMAGE,
        repo=repo,
        branch=branch,
        task=task,
        base_branch=base_branch,
        ai_command=ai_command,
        env={"GH_TOKEN": gh_token},
        mounts=[(str(auth_dir), "/home/gemini/.gemini", "rw")],
        tool_name="coding.gemini_cli_run",
        pr_prefix="gemini-cli",
        commit_prefix="gemini-cli",
        session_id=session_id,
        output_extractor=_extract_gemini_output,
    )


def register() -> None:
    register_tool(
        ToolDefinition(
            id="coding.gemini_cli_run",
            callable=gemini_cli_run,
            description=(
                "Spawn Google's Gemini CLI inside a sandboxed Docker container "
                "against a GitHub repo. Clones the repo, runs `gemini -p TASK "
                "--output-format json --yolo`, pushes a branch, opens a draft "
                "PR. Authenticates via your host ~/.gemini OAuth directory "
                "(run `gemini auth login` first). Args: repo (owner/name), "
                "branch, task, base_branch (default 'main'), model (default "
                "'gemini-2.5-pro'), include_all_files (load entire repo into "
                "context). Gated for approval; consumes Gemini subscription "
                "quota."
            ),
            approval_required=True,
            risk_level="high",
        )
    )
