"""Shared sandboxed-container runner for coding tools.

Both ``gemini_cli_run`` and ``antigravity_run`` follow the same recipe:

1. ``docker run --rm`` against a pre-built image that contains ``git``, ``gh``,
   and the chosen Google AI CLI.
2. Inside the container: clone the target GitHub repo, check out a fresh
   branch, run the CLI in headless mode, commit anything it touched, push
   the branch, open a draft PR.
3. Stream stdout/stderr line-by-line back to the chat UI through the
   existing ``chat.streaming.notify_session`` hook.
4. Return a structured ``ToolResult`` with the PR URL, AI output, and
   stdout/stderr tails.

The two tools differ only in:

* image tag
* ``ai_command`` -- the bash fragment that invokes the AI CLI
* the env vars they need (Gemini API key vs. Antigravity token)
* an optional ``output_extractor`` callback that pulls a structured
  ``response`` field out of stdout (e.g. Gemini emits JSON).
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


CONTAINER_TIMEOUT_DEFAULT = int(os.environ.get("CODING_CONTAINER_TIMEOUT_SECONDS", "1800"))


# ---------------------------------------------------------------------------
# Streaming subprocess
# ---------------------------------------------------------------------------
def _emit_from_session(session_id: str, payload: dict[str, Any]) -> None:
    if not session_id:
        return
    try:
        from chat.streaming import notify_session

        notify_session(session_id, payload)
    except Exception as exc:  # noqa: BLE001
        logger.debug("coding stream notify failed: %s", exc)


def _stream_subprocess(
    cmd: list[str],
    *,
    session_id: str,
    tool_name: str,
    timeout: int,
) -> tuple[int, list[str], list[str]]:
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def _pump(stream, sink, tag):
        for raw in iter(stream.readline, ""):
            line = raw.rstrip("\n")
            if not line:
                continue
            sink.append(line)
            _emit_from_session(
                session_id,
                {
                    "type": "tool_result",
                    "name": tool_name,
                    "content": f"[{tag}] {line}",
                },
            )
        stream.close()

    proc = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    t_out = threading.Thread(target=_pump, args=(proc.stdout, stdout_lines, "out"), daemon=True)
    t_err = threading.Thread(target=_pump, args=(proc.stderr, stderr_lines, "err"), daemon=True)
    t_out.start()
    t_err.start()
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        rc = -1
        stderr_lines.append(f"timeout after {timeout}s")
    t_out.join(timeout=2)
    t_err.join(timeout=2)
    return rc, stdout_lines, stderr_lines


# ---------------------------------------------------------------------------
# Entrypoint script builder
# ---------------------------------------------------------------------------
def _build_entrypoint_script(
    repo: str,
    branch: str,
    task: str,
    base_branch: str,
    ai_command: str,
    pr_prefix: str,
    commit_prefix: str,
) -> str:
    """Bash that the container runs as a single arg to entrypoint sh -lc.

    ``ai_command`` is the chunk that actually invokes the AI CLI. It must
    handle shell-quoting of the task itself (we expose the task via the
    ``TASK_PROMPT`` env var to avoid double-quoting headaches).
    """
    pr_title = f"{pr_prefix}: {task[:80]}"
    commit_msg = f"{commit_prefix}: {task[:60]}"
    return "\n".join(
        [
            "set -eo pipefail",
            f'git config --global user.email "{commit_prefix}@surajclaw.local"',
            f'git config --global user.name "SurajClaw {commit_prefix}"',
            f"gh repo clone {shlex.quote(repo)} /work/repo",
            "cd /work/repo",
            (
                f"git checkout -b {shlex.quote(branch)} "
                f"origin/{shlex.quote(base_branch)} 2>/dev/null "
                f"|| git checkout -b {shlex.quote(branch)}"
            ),
            ai_command,
            "git add -A",
            f"git commit -m {shlex.quote(commit_msg)} || true",
            f"git push -u origin {shlex.quote(branch)}",
            (
                f"gh pr create --draft "
                f"--title {shlex.quote(pr_title)} "
                f"--body {shlex.quote(task)} "
                f"--base {shlex.quote(base_branch)} "
                f"--head {shlex.quote(branch)} || true"
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_coding_container(
    *,
    image: str,
    repo: str,
    branch: str,
    task: str,
    base_branch: str,
    ai_command: str,
    env: dict[str, str],
    tool_name: str,
    pr_prefix: str,
    commit_prefix: str,
    mounts: list[tuple[str, str, str]] | None = None,
    session_id: str = "",
    timeout: int = CONTAINER_TIMEOUT_DEFAULT,
    output_extractor: Callable[[list[str]], tuple[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Drive one coding-container run end to end. Returns a tool-result dict.

    ``mounts`` is a list of ``(host_path, container_path, mode)`` tuples where
    mode is ``"ro"`` or ``"rw"``. Used to pipe host-side OAuth credential
    directories (``~/.gemini``, ``~/.config/antigravity``) into the sandbox.

    ``output_extractor`` is given the full stdout line list and may return
    ``(ai_output_text, structured_dict)``. When omitted, we fall back to a
    short tail of stdout.
    """
    if not repo or not branch or not task:
        return {
            "ok": False,
            "output": "repo, branch, and task are all required",
            "error": "missing_args",
        }

    script = _build_entrypoint_script(
        repo=repo,
        branch=branch,
        task=task,
        base_branch=base_branch,
        ai_command=ai_command,
        pr_prefix=pr_prefix,
        commit_prefix=commit_prefix,
    )

    cmd = ["docker", "run", "--rm"]
    for host, container, mode in mounts or []:
        if host and container:
            cmd += ["-v", f"{host}:{container}:{mode}"]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    # Make the task available to the AI command via env so the script can
    # reference "$TASK_PROMPT" instead of needing more shell quoting.
    cmd += ["-e", f"TASK_PROMPT={task}"]
    cmd += [image, script]

    rc, stdout_lines, stderr_lines = _stream_subprocess(
        cmd, session_id=session_id, tool_name=tool_name, timeout=timeout
    )

    pr_url = ""
    for line in stdout_lines + stderr_lines:
        if "github.com/" in line and "/pull/" in line:
            pr_url = line.strip()
            break

    ai_output = ""
    extra_structured: dict[str, Any] = {}
    if output_extractor is not None:
        try:
            ai_output, extra_structured = output_extractor(stdout_lines)
        except Exception as exc:  # noqa: BLE001
            logger.warning("output_extractor failed for %s: %s", tool_name, exc)

    if rc != 0:
        return {
            "ok": False,
            "output": (
                f"{tool_name} exited {rc}.\nLast stderr:\n"
                + "\n".join(stderr_lines[-20:])
            ),
            "error": "container_failed",
            "structured": {
                "exit_code": rc,
                "pr_url": pr_url,
                "stdout_tail": stdout_lines[-40:],
                "stderr_tail": stderr_lines[-40:],
                "ai_output": ai_output,
                **extra_structured,
            },
        }

    short_output = ai_output or "\n".join(stdout_lines[-20:])
    return {
        "ok": True,
        "output": (
            f"{tool_name} finished. Draft PR: {pr_url or '(check output for the URL)'}\n"
            f"AI output:\n{short_output[:1200]}"
        ),
        "structured": {
            "exit_code": rc,
            "pr_url": pr_url,
            "stdout_tail": stdout_lines[-40:],
            "stderr_tail": stderr_lines[-40:],
            "ai_output": ai_output,
            **extra_structured,
        },
    }
