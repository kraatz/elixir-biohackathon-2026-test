# Backlog

Deferred items with no slice yet. One line each: the item, where it came from (PR, review thread, spec), and
why it waits. The PR that fixes an item deletes its line. See
`.methodology/shared/guides/development-workflow.md`, *Deferred items land somewhere durable*.

<!-- - <item> — from <PR #n / review thread / spec Inputs for>, waits because <reason>. -->

- Wire the methodology's CI on the fork: copy `.methodology/template/.github/workflows/` (`agent.yml`, `agent-review.yml` with the test command, `pr-checks.yml` with `exclude` for `platform/**/package-lock.json`, `**/uv.lock`, `platform/agui/pydantic-ai-agent/tests/fixtures/*`), install agent-action's Apps on the fork, add it to the runner's `repos`, create the labels, turn on auto-delete of head branches and the DCO app; then drop the review/approval lines in `CLAUDE.md`, *Overrides* — from the methodology adoption (`change/adopt-methodology`), waits because `thodkatz/agent-action` is private and the fork has no access to it yet, and the user chose the local side first.
- Fork-only workflows must not run on upstream PRs: when the CI above lands, check that `.github/workflows/` added on the fork stays out of upstream branches (`CLAUDE.md`, *Contributing upstream*: add `.github/workflows/agent*.yml` and `pr-checks.yml` to the fork-only list) — from the methodology adoption, waits on the item above.
