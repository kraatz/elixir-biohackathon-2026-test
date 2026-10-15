"""promptfoo Python provider: one AG-UI run against the SPE agent per test case.

    providers: [{id: "file://agui_provider.py", label: spe-agent}]

Environment (on the controller, never in the config):
  SPE_AGENT_URL           default http://127.0.0.1:8100/agent (through the SSH tunnel)
  SPE_AGENT_API_KEY       the agent's bearer key, or
  SPE_AGENT_API_KEY_FILE  a file holding it (output/<instance>/agent_api_key)

Returns {output: final assistant text, metadata: {tool_calls: [{id, name, args, result}],
run_id, thread_id, terminal, events}} or {error: ...} for an HTTP error, RUN_ERROR, a
timeout, a malformed event or a stream that ends without a terminal event. Optional
`vars.history` ([{role, content}]) is sent before the prompt as earlier turns. Uses
only the standard library; the bearer key is never logged or returned.
"""
from __future__ import annotations

import codecs
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

DEFAULT_URL = "http://127.0.0.1:8100/agent"
DEFAULT_TIMEOUT = 600.0


class StreamError(Exception):
    pass


class SSEParser:
    """Incremental server-sent events: bytes in (split anywhere), parsed JSON events out."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._buf = ""
        self._data: list[str] = []

    def feed(self, chunk: bytes) -> list[dict]:
        self._buf += self._decoder.decode(chunk)
        events = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            event = self._line(line.rstrip("\r"))
            if event is not None:
                events.append(event)
        return events

    def close(self) -> list[dict]:
        self._buf += self._decoder.decode(b"", final=True)
        events = []
        for line in (self._buf, ""):
            event = self._line(line.rstrip("\r"))
            if event is not None:
                events.append(event)
        self._buf = ""
        return events

    def _line(self, line: str) -> dict | None:
        if line == "":
            if not self._data:
                return None
            raw, self._data = "\n".join(self._data), []
            try:
                event = json.loads(raw)
            except ValueError:
                raise StreamError(f"malformed event: {raw[:200]!r}") from None
            if not isinstance(event, dict):
                raise StreamError("malformed event: not a JSON object")
            return event
        if line.startswith("data:"):
            value = line[5:]
            self._data.append(value[1:] if value.startswith(" ") else value)
        return None  # comments and other fields


class Accumulator:
    def __init__(self, run_id: str = "", thread_id: str = "") -> None:
        self.ids = {"run_id": run_id, "thread_id": thread_id}  # as sent; they match the agent's run log
        self.text: list[str] = []
        self.calls: dict[str, dict] = {}
        self.terminal: dict | None = None
        self.count = 0

    def add(self, event: dict) -> None:
        self.count += 1
        kind = event.get("type")
        if kind == "TOOL_CALL_START":
            cid = event.get("toolCallId", "")
            self.calls[cid] = {"id": cid, "name": event.get("toolCallName", ""), "args": "", "result": None}
        elif kind == "TOOL_CALL_ARGS" and event.get("toolCallId") in self.calls:
            self.calls[event["toolCallId"]]["args"] += event.get("delta", "")
        elif kind == "TOOL_CALL_RESULT" and event.get("toolCallId") in self.calls:
            self.calls[event["toolCallId"]]["result"] = event.get("content")
        elif kind == "TEXT_MESSAGE_CONTENT":
            self.text.append(event.get("delta", ""))
        elif kind in ("RUN_FINISHED", "RUN_ERROR") and self.terminal is None:
            self.terminal = event

    def result(self) -> dict:
        metadata = {"tool_calls": list(self.calls.values()), "terminal": (self.terminal or {}).get("type"),
                    "events": self.count, **self.ids}
        out: dict[str, Any] = {"output": "".join(self.text), "metadata": metadata}
        if self.terminal is None:
            out["error"] = "no terminal event: the stream ended early"
        elif self.terminal["type"] == "RUN_ERROR":
            out["error"] = f"RUN_ERROR: {str(self.terminal.get('message', ''))[:500]}"
        return out


def _key() -> str:
    key = os.environ.get("SPE_AGENT_API_KEY", "")
    path = os.environ.get("SPE_AGENT_API_KEY_FILE", "")
    if not key and path:
        with open(path) as f:
            key = f.read().strip()
    return key


def _messages(prompt: str, context: dict | None) -> list[dict]:
    history = ((context or {}).get("vars") or {}).get("history") or []
    if isinstance(history, str):
        history = json.loads(history)
    msgs = [{"id": str(uuid.uuid4()), "role": m["role"], "content": m["content"]} for m in history]
    return msgs + [{"id": str(uuid.uuid4()), "role": "user", "content": prompt}]


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    config = (options or {}).get("config") or {}
    url = config.get("url") or os.environ.get("SPE_AGENT_URL", DEFAULT_URL)
    timeout = float(config.get("timeout", DEFAULT_TIMEOUT))
    try:
        key = _key()
    except OSError as e:
        return {"error": f"cannot read SPE_AGENT_API_KEY_FILE: {e.strerror}"}
    if not key:
        return {"error": "set SPE_AGENT_API_KEY or SPE_AGENT_API_KEY_FILE"}
    body = {"threadId": f"eval-{uuid.uuid4()}", "runId": f"eval-{uuid.uuid4()}", "state": {}, "tools": [],
            "context": [], "forwardedProps": {}, "messages": _messages(prompt, context)}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "text/event-stream"})
    acc, parser = Accumulator(body["runId"], body["threadId"]), SSEParser()
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.urlopen(req, timeout=min(timeout, 120.0)) as resp:
            while chunk := resp.read1(65536):
                for event in parser.feed(chunk):
                    acc.add(event)
                if time.monotonic() > deadline:
                    raise TimeoutError(f"run exceeded {timeout:.0f} s")
            for event in parser.close():
                acc.add(event)
    except urllib.error.HTTPError as e:
        return {"error": f"agent answered HTTP {e.code}"}
    except (StreamError, UnicodeDecodeError) as e:
        res = acc.result()
        res["error"] = f"stream error: {e}"
        return res
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        res = acc.result()
        res["error"] = f"request failed: {type(e).__name__}: {getattr(e, 'reason', e)}"
        return res
    return acc.result()
