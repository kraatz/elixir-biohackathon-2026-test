#!/usr/bin/env python3
"""One AG-UI run against the SPE agent: it must call a tool and end with RUN_FINISHED.

Makes one LLM-backed run (a paid model call). The bearer key comes from the
SPE_AGENT_API_KEY environment variable, never from the command line. Prints a JSON
summary (tool names, terminal event, answer length) and exits 0 on success, 1 on any
failure (HTTP error, RUN_ERROR, no tool call, interrupted stream, timeout), 2 on usage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterable, Iterator

PROMPT = "List the registered workflows."


def parse_sse(lines: Iterable[str]) -> Iterator[dict]:
    """Server-sent events from text lines; multi-line data fields are joined with newlines."""
    data: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line:
            if data:
                yield json.loads("\n".join(data))
                data = []
        elif line.startswith("data:"):
            value = line[5:]
            data.append(value[1:] if value.startswith(" ") else value)
        # other fields (event:, id:, retry:) and comments (:) are ignored
    if data:
        yield json.loads("\n".join(data))


def verdict(events: list[dict]) -> tuple[bool, dict]:
    types = [e.get("type") for e in events]
    tools = [e.get("toolCallName") for e in events if e.get("type") == "TOOL_CALL_START"]
    answer = "".join(e.get("delta", "") for e in events if e.get("type") == "TEXT_MESSAGE_CONTENT")
    terminal = [t for t in types if t in ("RUN_FINISHED", "RUN_ERROR")]
    summary = {"tools": tools, "terminal": terminal[-1] if terminal else None, "answer_chars": len(answer),
               "events": len(events)}
    if "RUN_ERROR" in terminal:
        err = next(e for e in events if e.get("type") == "RUN_ERROR")
        summary["problem"] = f"RUN_ERROR: {str(err.get('message', ''))[:300]}"
    elif not terminal:
        summary["problem"] = "no terminal event: the stream was interrupted"
    elif terminal != ["RUN_FINISHED"] or types[-1] != "RUN_FINISHED":
        summary["problem"] = f"unexpected terminal events {terminal}"
    elif not tools:
        summary["problem"] = "no tool call"
    return "problem" not in summary, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8100/agent")
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--timeout", type=float, default=300.0, help="seconds for the whole run")
    args = ap.parse_args()
    key = os.environ.get("SPE_AGENT_API_KEY", "")
    if not key:
        print("SPE_AGENT_API_KEY is not set", file=sys.stderr)
        return 2
    body = {"threadId": f"smoke-{uuid.uuid4()}", "runId": f"smoke-{uuid.uuid4()}", "state": {}, "tools": [],
            "context": [], "forwardedProps": {},
            "messages": [{"id": str(uuid.uuid4()), "role": "user", "content": args.prompt}]}
    req = urllib.request.Request(args.url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "text/event-stream"})
    deadline = time.monotonic() + args.timeout
    events: list[dict] = []

    def lines(resp):
        for raw in resp:  # each read is bounded by the socket timeout
            if time.monotonic() > deadline:
                raise TimeoutError(f"run exceeded {args.timeout:.0f} s")
            yield raw.decode("utf-8", "replace")

    try:
        with urllib.request.urlopen(req, timeout=min(args.timeout, 120)) as resp:
            for event in parse_sse(lines(resp)):
                events.append(event)
    except urllib.error.HTTPError as e:
        print(f"agent answered HTTP {e.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        print(f"run failed: {type(e).__name__}: {e}", file=sys.stderr)
        ok, summary = verdict(events)
        print(json.dumps(summary))
        return 1
    ok, summary = verdict(events)
    print(json.dumps(summary))
    if not ok:
        print(summary["problem"], file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
