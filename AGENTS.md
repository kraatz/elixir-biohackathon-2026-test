# elixir-biohackathon-2026-test

Threat models for agents in Secure Processing Environments (SPEs) and the
Ansible automation that builds SPE evaluation instances. This file is the
guide for humans and coding agents working in this repository.

| Path | What |
|---|---|
| `threats/`, `vocabulary.yaml`, `validate.py` | Threat model catalog (`TM-NNN-*.md`), its controlled vocabulary and validator |
| `ansible/` | Playbooks that create, verify and destroy one SPE instance (`ansible/README.md`) |
| `agent/` | Pydantic AI pentest agent served over AG-UI (in progress) |
| `dev/` | Development helpers: dummy dataset generator, tests for host-side scripts |
| `docs/specs/`, `docs/plans/` | Design specs and implementation plans |

## Working rules

- **Commit each coherent change** with a short imperative subject, and add a body saying why when the subject doesn't. Run `git status` and `git diff --staged` first, and stage files by name rather than with `git add -A`.
- **Never commit secrets**: real instance files (`ansible/instances/*.yml` other than `example.yml` and `*.example.yml`, ignored by git) carry the seed that reproduces every canary. Also never commit `ansible/output/`, `canaries.json`, keys, `clouds.yaml` or `.env` files.
- **Do not push**, rewrite history or force anything unless asked. Pushing is the repository owner's call.
- **Paid model calls need the human's OK** before they run. The local Anthropic provider accepts only `claude-haiku-5-5`.
- **Follow the plan's rulings discipline**: when work departs from a plan, record the decision, why, and its cost if wrong in that plan's progress file.

## Running things

```bash
uv run --with pyyaml --with python-frontmatter python validate.py   # threat catalog
uv run --with pytest pytest dev/tests -q             # dataset generator, host preflight
(cd agent && uv run --group dev pytest -q)           # agent
cd ansible && ansible-playbook playbooks/create.yml -e @instances/<name>.yml </dev/null
```

Ansible needs a blocking stdin here: always run it with `</dev/null`, from
`ansible/`. The collections come from the system Ansible package.

## Work in progress: AG-UI agent frontend (handed off)

Plan `docs/plans/2026-10-15-agui-frontend.md`, from spec
`docs/specs/2026-10-15-agui-frontend-design.md`. Implementation is on branch
`agent-agui-frontend-impl`, cut from `agent-agui-frontend` at `c5960c6`. It has
its own branch because the main working copy holds `agent-agui-frontend`;
fast-forward that branch to this one once the work is accepted. Nothing is pushed.

**The handoff.** The first implementation session stopped partway, on 2026-10-15,
and passed the job to a new session at the user's request. Its record is
[`docs/plans/2026-10-15-agui-frontend-progress.md`](docs/plans/2026-10-15-agui-frontend-progress.md):
the status of each task with its evidence, every departure from the plan with
its cost if wrong, the Open WebUI behaviour to copy, and the local files that
are not in git. That file is the source of truth for where the work stands.
Update it as tasks finish, and commit it with the work.

At the handoff:

- Done: Task 1 (existing-VM provisioning, `dec71fa`), Task 2 (dummy dataset, `9d45036`), Task 6 (agent config, `80b2ae9`).
- Task 3 (SPE stack on the dev VM): the first full run and the endpoint checks passed. On the re-run, `workflow_stack : Whole stack up` reported `changed`; this has not been debugged. `verify.yml` and the README note are still open.
- Task 7: the open-terminal 0.12.4 OpenAPI fixture and `agent/tests/test_sandbox.py` are committed (`1904b22`). The module they test, `agent/src/spe_agent/sandbox.py`, is not written. The previous session stopped while writing it and left nothing behind, so write it fresh against those tests.
- Not started: Tasks 4, 5 and 8–13. No paid model calls have been made.

**To resume**, start a session in the worktree
`.claude/worktrees/agui-impl` (or a fresh checkout of the branch). Read the
progress file, then the plan, and continue at the first task not marked done.
The dev VM already runs the `dev-local` instance. Its private instance file
`ansible/instances/dev-local.yml` and its `ansible/output/dev-local/` exist
only in that worktree.
