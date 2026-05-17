"""Non-interactive smoke test for the SurajClaw chat agent.

Connects to the local WebSocket using the same credentials the CLI uses,
fires a sequence of sample prompts (one per session-turn), and prints the
frames that come back. Designed to exercise:

* general / web search
* google_workspace (gmail read)
* memory recall

Run from the repo root after `./start.sh` is up:

    .venv/bin/python scripts/smoke_agent.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from urllib.parse import urlencode

import websockets

sys.path.insert(0, "surajclaw")
from clawcli.config import http_to_ws, load_credentials  # noqa: E402

PROMPTS: list[str] = [
    "Quick health check: respond with 'pong' and nothing else.",
    "Read my last 3 unread emails from Gmail and summarize each in one line.",
    "What's the most recent thing I asked you to remember? Search your memory.",
    "Search the web for today's headline about AI and give me one sentence.",
]

PER_TURN_BUDGET = 90.0  # seconds


def _short(s: str, n: int = 180) -> str:
    s = s.replace("\n", " ⏎ ")
    return s if len(s) <= n else s[:n] + "..."


async def _run_one_turn(ws: websockets.WebSocketClientProtocol, prompt: str, idx: int) -> None:
    print(f"\n\033[1;36m=== Q{idx}: {prompt}\033[0m")
    await ws.send(json.dumps({"message": prompt}))
    started = time.monotonic()
    stream = ""
    while True:
        if time.monotonic() - started > PER_TURN_BUDGET:
            print(f"\033[1;31m[timeout after {PER_TURN_BUDGET}s — aborting turn]\033[0m")
            try:
                await ws.send(json.dumps({"message": "/stop"}))
            except Exception:
                pass
            return
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        except asyncio.TimeoutError:
            print("\033[2m  · still waiting...\033[0m")
            continue
        try:
            frame = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        ftype = frame.get("type")
        if ftype == "token":
            chunk = frame.get("content") or ""
            stream += chunk
            print(chunk, end="", flush=True)
        elif ftype == "tool_call":
            name = frame.get("name")
            args = _short(json.dumps(frame.get("args") or {}, default=str), 120)
            print(f"\n\033[33m  → tool {name}({args})\033[0m")
        elif ftype == "tool_result":
            name = frame.get("name")
            content = frame.get("content")
            if not isinstance(content, str):
                content = json.dumps(content, default=str)
            print(f"\033[32m  ← {name}: {_short(content)}\033[0m")
        elif ftype == "node_update":
            print(f"\033[2m  [{frame.get('node')}]\033[0m")
        elif ftype == "system":
            print(f"\033[2;3m  (system) {_short(str(frame.get('content') or ''))}\033[0m")
        elif ftype == "error":
            print(f"\033[1;31m  error: {frame.get('content')}\033[0m")
        elif ftype == "final":
            content = frame.get("content")
            if content and not stream:
                print(f"\n{content}")
            print(f"\n\033[2m  ─── final ({time.monotonic()-started:.1f}s)\033[0m")
        elif ftype == "done":
            print()
            return
        elif ftype == "approval":
            # auto-reject in smoke test
            print(f"\033[33m  ⚠ approval requested ({frame.get('description')}) — auto-rejecting\033[0m")
            try:
                req_id = frame.get("request_id")
                from clawcli.http import ApiClient
                creds = load_credentials()
                ApiClient(server=creds.server, token=creds.token).post(
                    f"/approval/{req_id}/respond/",
                    {"decision": "rejected", "responded_by": "smoke"},
                )
            except Exception as exc:
                print(f"  approval respond failed: {exc}")
        else:
            print(f"\033[2;35m  ?? {ftype}: {_short(json.dumps(frame, default=str))}\033[0m")


async def main() -> int:
    creds = load_credentials()
    if not creds:
        print("No stored credentials. Run `surajclaw login` first.", file=sys.stderr)
        return 1

    session_id = str(uuid.uuid4())
    ws_base = http_to_ws(creds.server).rstrip("/")
    url = f"{ws_base}/ws/chat/{session_id}/?{urlencode({'token': creds.token})}"
    print(f"\033[2mconnecting to {ws_base}  session={session_id[:8]}…\033[0m")

    async with websockets.connect(url, max_size=2**22) as ws:
        # drain any opening system frame
        try:
            opener = await asyncio.wait_for(ws.recv(), timeout=2.0)
            print(f"\033[2m{_short(opener)}\033[0m")
        except asyncio.TimeoutError:
            pass

        for i, prompt in enumerate(PROMPTS, 1):
            try:
                await _run_one_turn(ws, prompt, i)
            except websockets.ConnectionClosed as exc:
                print(f"\033[1;31mconnection closed: {exc}\033[0m")
                break
            if i < len(PROMPTS):
                print("\033[2m  (waiting 65s to dodge Gemini per-minute RPM)\033[0m")
                await asyncio.sleep(65)
    print("\n\033[1mdone.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
