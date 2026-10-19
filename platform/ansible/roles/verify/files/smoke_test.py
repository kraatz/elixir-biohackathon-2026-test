#!/usr/bin/env python3
"""Submit the smoke workflow through WES with a DRS input and wait for COMPLETE."""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from urllib.request import Request, urlopen


def multipart(fields: dict) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def get_json(url: str):
    with urlopen(Request(url), timeout=60) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True, help="https://HOST/ga4gh/wes/v1")
    ap.add_argument("--workflow-url", required=True)
    ap.add_argument("--drs-uri", required=True)
    ap.add_argument("--engine-version", default="25.04.3")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    body, ctype = multipart({
        "workflow_type": "NFL",
        "workflow_type_version": args.engine_version,
        "workflow_url": args.workflow_url,
        "workflow_params": json.dumps({"input": {"drs_uri": args.drs_uri}}),
    })
    req = Request(args.api.rstrip("/") + "/runs", data=body, headers={"Content-Type": ctype}, method="POST")
    with urlopen(req, timeout=60) as r:
        run_id = json.load(r)["run_id"]
    print(f"run_id={run_id}", file=sys.stderr)

    deadline = time.time() + args.timeout
    state = "UNKNOWN"
    while time.time() < deadline:
        state = get_json(f"{args.api.rstrip('/')}/runs/{run_id}/status")["state"]
        if state == "COMPLETE":
            break
        if state in ("EXECUTOR_ERROR", "SYSTEM_ERROR", "CANCELED"):
            print(json.dumps(get_json(f"{args.api.rstrip('/')}/runs/{run_id}"), indent=2), file=sys.stderr)
            print(json.dumps({"run_id": run_id, "state": state}))
            return 1
        time.sleep(5)
    print(json.dumps({"run_id": run_id, "state": state}))
    return 0 if state == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
