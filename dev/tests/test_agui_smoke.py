"""agui_smoke.py: one AG-UI run must call a tool and finish; anything else exits nonzero."""
import importlib.util
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ansible" / "roles" / "agui" / "files" / "agui_smoke.py"


@pytest.fixture
def smoke():
    spec = importlib.util.spec_from_file_location("agui_smoke", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sse(*events):
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events)


OK = [{"type": "RUN_STARTED"}, {"type": "TOOL_CALL_START", "toolCallName": "run_command", "toolCallId": "c1"},
      {"type": "TOOL_CALL_RESULT", "toolCallId": "c1", "content": "x"},
      {"type": "TEXT_MESSAGE_CONTENT", "delta": "hello"}, {"type": "RUN_FINISHED"}]


def test_parse_handles_split_lines_crlf_comments_and_multiline_data(smoke):
    raw = ": keepalive\r\n\r\ndata: {\"type\":\r\ndata:  \"RUN_STARTED\"}\r\n\r\n" + sse({"type": "RUN_FINISHED"})
    lines = []
    buf = ""
    for i in range(0, len(raw), 3):  # 3-byte network chunks
        buf += raw[i:i + 3]
        *done, buf = buf.split("\n")
        lines += [d + "\n" for d in done]
    events = list(smoke.parse_sse(lines))
    assert [e["type"] for e in events] == ["RUN_STARTED", "RUN_FINISHED"]


def test_verdict_ok(smoke):
    ok, summary = smoke.verdict(OK)
    assert ok and summary["tools"] == ["run_command"] and summary["terminal"] == "RUN_FINISHED"


@pytest.mark.parametrize("events,why", [
    ([{"type": "RUN_STARTED"}, {"type": "TEXT_MESSAGE_CONTENT", "delta": "hi"}, {"type": "RUN_FINISHED"}], "no tool call"),
    (OK[:-1] + [{"type": "RUN_ERROR", "message": "limit"}], "RUN_ERROR"),
    (OK[:-1], "no terminal event"),
    (OK + [{"type": "RUN_ERROR", "message": "late"}], "RUN_ERROR"),
])
def test_verdict_failures(smoke, events, why):
    ok, summary = smoke.verdict(events)
    assert not ok and why in summary["problem"]


class Agent(BaseHTTPRequestHandler):
    body = sse(*OK)
    seen = {}

    def do_POST(self):
        Agent.seen = {"auth": self.headers.get("authorization"),
                      "input": json.loads(self.rfile.read(int(self.headers["content-length"])))}
        if self.headers.get("authorization") != "Bearer good":
            self.send_response(401); self.end_headers(); return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.wfile.write(Agent.body.encode())

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Agent)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/agent"
    srv.shutdown()


def run(url, key, body=None):
    if body is not None:
        Agent.body = body
    return subprocess.run([sys.executable, str(SCRIPT), "--url", url, "--timeout", "10"],
                          env={"SPE_AGENT_API_KEY": key}, capture_output=True, text=True)


def test_cli_success_sends_a_valid_run_input(server):
    res = run(server, "good", sse(*OK))
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["tools"] == ["run_command"]
    inp = Agent.seen["input"]
    assert inp["messages"][0]["role"] == "user" and inp["threadId"] and inp["runId"]
    assert "good" not in res.stdout + res.stderr


def test_cli_fails_on_401_without_echoing_the_key(server):
    res = run(server, "wrong-key-value", sse(*OK))
    assert res.returncode != 0 and "401" in res.stderr and "wrong-key-value" not in res.stderr + res.stdout


def test_cli_fails_on_run_error(server):
    res = run(server, "good", sse(*(OK[:-1] + [{"type": "RUN_ERROR", "message": "boom"}])))
    assert res.returncode != 0 and "RUN_ERROR" in res.stderr


def test_cli_needs_the_key():
    res = subprocess.run([sys.executable, str(SCRIPT), "--url", "http://127.0.0.1:9/agent"], env={},
                         capture_output=True, text=True)
    assert res.returncode == 2 and "SPE_AGENT_API_KEY" in res.stderr
