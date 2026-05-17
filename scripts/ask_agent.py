"""One-shot agent query — send a single prompt and stream until done.

Usage:
    .venv/bin/python scripts/ask_agent.py "your question here"
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

BUDGET_SECONDS = 240.0


def _short(s: str, n: int = 200) -> str:
    s = s.replace("\n", " ⏎ ")
    return s if len(s) <= n else s[:n] + "..."


async def _run(prompt: str) -> int:
    creds = load_credentials()
    if not creds:
        print("No stored credentials. Run `surajclaw login` first.", file=sys.stderr)
        return 1

    session_id = str(uuid.uuid4())
    ws_base = http_to_ws(creds.server).rstrip("/")
    url = f"{ws_base}/ws/chat/{session_id}/?{urlencode({'token': creds.token})}"
    print(f"\033[2mconnecting to {ws_base}  session={session_id[:8]}…\033[0m")

    async with websockets.connect(url, max_size=2**22) as ws:
        try:
            opener = await asyncio.wait_for(ws.recv(), timeout=2.0)
            print(f"\033[2m{_short(opener)}\033[0m")
        except asyncio.TimeoutError:
            pass

        print(f"\n\033[1;36m>>> {prompt}\033[0m\n")
        await ws.send(json.dumps({"message": prompt}))
        started = time.monotonic()
        while True:
            if time.monotonic() - started > BUDGET_SECONDS:
                print(f"\033[1;31m[budget exceeded — sending /stop]\033[0m")
                try:
                    await ws.send(json.dumps({"message": "/stop"}))
                except Exception:
                    pass
                return 2
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - started
                print(f"\033[2m  · idle ({elapsed:.0f}s elapsed)\033[0m")
                continue

            try:
                frame = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue

            ftype = frame.get("type")
            if ftype == "token":
                print(frame.get("content") or "", end="", flush=True)
            elif ftype == "tool_call":
                args = _short(json.dumps(frame.get("args") or {}, default=str), 200)
                print(f"\n\033[33m  → tool {frame.get('name')}({args})\033[0m")
            elif ftype == "tool_result":
                c = frame.get("content")
                if not isinstance(c, str):
                    c = json.dumps(c, default=str)
                print(f"\033[32m  ← {frame.get('name')}: {_short(c, 400)}\033[0m")
            elif ftype == "node_update":
                print(f"\033[2m  [{frame.get('node')}]\033[0m")
            elif ftype == "system":
                print(f"\033[2;3m  (system) {_short(str(frame.get('content') or ''))}\033[0m")
            elif ftype == "error":
                print(f"\033[1;31m  error: {frame.get('content')}\033[0m")
            elif ftype == "final":
                content = frame.get("content")
                if content:
                    print(f"\n{content}")
                print(f"\n\033[2m  ─── final ({time.monotonic()-started:.1f}s)\033[0m")
            elif ftype == "done":
                print()
                return 0
            else:
                print(f"\n\033[2;35m  ?? {ftype}: {_short(json.dumps(frame, default=str))}\033[0m")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: ask_agent.py 'your question'", file=sys.stderr)
        raise SystemExit(2)
    prompt = " ".join(sys.argv[1:])
    raise SystemExit(asyncio.run(_run(prompt)))
