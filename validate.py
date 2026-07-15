#!/usr/bin/env python3
"""Validate threat model entries against vocabulary.yaml and conventions.

Checks per entry (threats/TM-*.md):
  - frontmatter parses and all required fields are present
  - `id` has format TM-NNN and matches the filename prefix
  - no duplicate IDs across the catalog
  - `assets`, `stride`, `agent-capabilities` only use vocabulary.yaml values
  - `related` entries reference existing IDs, are not self-references,
    and are symmetric (if A lists B, B must list A)
  - `last_reviewed` is a valid ISO date (YYYY-MM-DD)

Usage:
    python validate.py [--threats-dir threats] [--vocab vocabulary.yaml]

Exit code 0 if all checks pass, 1 otherwise.

Dependencies:
    pip install pyyaml python-frontmatter
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

import frontmatter
import yaml

ID_PATTERN = re.compile(r"^TM-\d{3}$")
FILENAME_PATTERN = re.compile(r"^(TM-\d{3})-[a-z0-9-]+\.md$")

REQUIRED_FIELDS = [
    "id",
    "name",
    "description",
    "assets",
    "stride",
    "agent-capabilities",
    "related",
    "references",
    "last_reviewed",
]

# frontmatter field -> vocabulary.yaml section
VOCAB_FIELDS = {
    "assets": "assets",
    "stride": "stride",
    "agent-capabilities": "agent-capabilities",
}


def load_vocabulary(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        vocab = yaml.safe_load(f)
    for section in VOCAB_FIELDS.values():
        if section not in vocab or not isinstance(vocab[section], dict):
            sys.exit(f"vocabulary file {path} is missing section '{section}'")
        # Guard against a silently broken/emptied vocabulary.
        if len(vocab[section]) == 0:
            sys.exit(f"vocabulary section '{section}' in {path} is empty")
    return vocab


def check_entry(path: Path, post: frontmatter.Post, vocab: dict) -> list[str]:
    errors = []
    meta = post.metadata

    for field in REQUIRED_FIELDS:
        if field not in meta:
            errors.append(f"missing required field '{field}'")
    if errors:
        return errors  # further checks need the fields

    entry_id = meta["id"]
    if not isinstance(entry_id, str) or not ID_PATTERN.match(entry_id):
        errors.append(f"id '{entry_id}' does not match format TM-NNN")

    m = FILENAME_PATTERN.match(path.name)
    if not m:
        errors.append(
            f"filename '{path.name}' does not match pattern TM-NNN-short-slug.md"
        )
    elif m.group(1) != entry_id:
        errors.append(
            f"filename prefix '{m.group(1)}' does not match id '{entry_id}'"
        )

    for field, section in VOCAB_FIELDS.items():
        values = meta[field]
        if not isinstance(values, list) or not values:
            errors.append(f"'{field}' must be a non-empty list")
            continue
        for value in values:
            if value not in vocab[section]:
                errors.append(
                    f"unknown {field} value '{value}' "
                    f"(not in vocabulary.yaml [{section}])"
                )

    related = meta["related"]
    if not isinstance(related, list):
        errors.append("'related' must be a list (use [] if empty)")
    else:
        for rid in related:
            if not isinstance(rid, str) or not ID_PATTERN.match(rid):
                errors.append(f"related id '{rid}' does not match format TM-NNN")
            elif rid == entry_id:
                errors.append("'related' must not reference the entry itself")

    lr = meta["last_reviewed"]
    # PyYAML parses bare YYYY-MM-DD into a date object already; accept both.
    if not isinstance(lr, datetime.date):
        try:
            datetime.date.fromisoformat(str(lr))
        except ValueError:
            errors.append(
                f"last_reviewed '{lr}' is not a valid ISO date (YYYY-MM-DD)"
            )

    return errors


def check_catalog(entries: dict[str, dict]) -> list[str]:
    """Cross-entry checks: duplicate ids, dangling and asymmetric relations."""
    errors = []

    ids_seen: dict[str, str] = {}
    for fname, meta in entries.items():
        entry_id = meta.get("id")
        if entry_id in ids_seen:
            errors.append(
                f"duplicate id '{entry_id}' in {fname} and {ids_seen[entry_id]}"
            )
        else:
            ids_seen[entry_id] = fname

    by_id = {meta["id"]: (fname, meta) for fname, meta in entries.items()}
    for entry_id, (fname, meta) in by_id.items():
        for rid in meta.get("related", []):
            if rid not in by_id:
                errors.append(f"{fname}: related id '{rid}' does not exist")
            elif entry_id not in by_id[rid][1].get("related", []):
                errors.append(
                    f"{fname}: relation to '{rid}' is not symmetric "
                    f"({rid} does not list '{entry_id}' back)"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threats-dir", default="threats", type=Path)
    parser.add_argument("--vocab", default="vocabulary.yaml", type=Path)
    args = parser.parse_args()

    if not args.threats_dir.is_dir():
        sys.exit(f"threats directory '{args.threats_dir}' not found")
    vocab = load_vocabulary(args.vocab)

    files = sorted(args.threats_dir.glob("TM-*.md"))
    if not files:
        sys.exit(f"no TM-*.md files found in '{args.threats_dir}'")

    failed = False
    entries: dict[str, dict] = {}

    for path in files:
        try:
            post = frontmatter.load(path)
        except Exception as exc:  # malformed YAML, encoding issues, ...
            print(f"FAIL {path.name}: cannot parse frontmatter: {exc}")
            failed = True
            continue

        errors = check_entry(path, post, vocab)
        if errors:
            failed = True
            print(f"FAIL {path.name}")
            for err in errors:
                print(f"  - {err}")
        else:
            entries[path.name] = post.metadata

    catalog_errors = check_catalog(entries)
    if catalog_errors:
        failed = True
        print("FAIL catalog-level checks")
        for err in catalog_errors:
            print(f"  - {err}")

    if failed:
        return 1
    print(f"OK: {len(files)} entries validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())