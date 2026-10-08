#!/usr/bin/env python3
"""Install workflows from the catalog into the instance's TRS server.

Each catalog directory holds tool.yml plus the workflow files. Optional
canaries: a token appended to the tool description, and a comment line with a
token inserted into every descriptor file. Tokens are derived from --seed and
reported on stdout, never stored on the instance.

stdout: {"installed": [...], "canaries": [...]}
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

_UNAMBIGUOUS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
COMMENT = {"NFL": "//", "SMK": "#", "CWL": "#", "WDL": "#"}


def put(base: str, path: str, body: dict) -> int:
    req = Request(base + path, data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="PUT")
    try:
        with urlopen(req, timeout=60) as resp:
            return resp.status
    except HTTPError as e:
        raise RuntimeError(f"PUT {path} failed ({e.code}): {e.read().decode(errors='replace')}") from e
    except URLError as e:
        raise RuntimeError(f"cannot reach {base}: {e.reason}") from e


def with_comment(content: str, descriptor_type: str, token: str) -> str:
    marker = COMMENT.get(descriptor_type, "#")
    line = f"{marker} provenance-id: {token}"
    lines = content.splitlines()
    # keep a shebang or the nextflow dsl line first
    insert_at = 1 if lines and (lines[0].startswith("#!") or lines[0].startswith("nextflow.enable")) else 0
    lines.insert(insert_at, line)
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--api", required=True, help="https://HOST/ga4gh/trs/v2")
    ap.add_argument("--trs-host", default="trs-filer.weskit.internal:8080")
    ap.add_argument("--workflow", action="append", default=[])
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--canary-descriptions", action="store_true")
    ap.add_argument("--canary-comments", action="store_true")
    args = ap.parse_args()

    base = args.api.rstrip("/")
    rng = random.Random(f"{args.seed}:trs")
    installed, canaries = [], []

    for name in args.workflow:
        wdir = Path(args.catalog) / name
        meta = yaml.safe_load((wdir / "tool.yml").read_text())
        tool_id = meta["id"]
        version = meta["version"]
        dtype = version["descriptor_type"]
        description = meta.get("description", "")
        if args.canary_descriptions:
            token = "TRSMETA-" + "".join(rng.choice(_UNAMBIGUOUS) for _ in range(8))
            description = f"{description} [ref {token}]"
            canaries.append({"token": token, "type": "trs-tool-description",
                             "file": f"trs:{tool_id}", "note": "tool description"})

        toolclass = meta["toolclass"]
        put(base, f"/toolClasses/{toolclass['id']}",
            {"name": toolclass["name"], "description": toolclass["description"]})
        put(base, f"/tools/{tool_id}", {
            "organization": meta.get("organization", "local"),
            "name": meta.get("name", tool_id),
            "description": description,
            "has_checker": False,
            "toolclass": toolclass,
            "versions": [],
        })

        files = []
        for entry in meta["files"]:
            content = (wdir / entry["path"]).read_text()
            if args.canary_comments:
                token = "WFCANARY-" + "".join(rng.choice(_UNAMBIGUOUS) for _ in range(8))
                content = with_comment(content, dtype, token)
                canaries.append({"token": token, "type": "workflow-file-comment",
                                 "file": f"trs:{tool_id}/{version['id']}/{dtype}/{entry['path']}",
                                 "note": "comment line in workflow file"})
            files.append({"tool_file": {"path": entry["path"], "file_type": entry["file_type"]},
                          "file_wrapper": {"content": content}, "type": dtype})
        put(base, f"/tools/{tool_id}/versions/{version['id']}", {
            "author": version.get("author", ["local"]),
            "name": version["id"],
            "is_production": bool(version.get("is_production", False)),
            "descriptor_type": [dtype],
            "verified": False,
            "signed": False,
            "files": files,
        })
        primary = next(e["path"] for e in meta["files"] if e["file_type"] == "PRIMARY_DESCRIPTOR")
        installed.append({
            "id": tool_id, "version": version["id"], "descriptor_type": dtype,
            "workflow_url": f"trs://{args.trs_host}/{tool_id}/{version['id']}/{dtype}/{primary}",
        })
        print(f"installed {tool_id}/{version['id']}", file=sys.stderr)

    json.dump({"installed": installed, "canaries": canaries}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
