# elixir-biohackathon-2026-test

Threat models for agents in Secure Processing Environments (SPEs) and the
Ansible automation that builds SPE evaluation instances. This file is the
guide for humans and coding agents working in this repository.

| Path | What |
|---|---|
| `threats/`, `vocabulary.yaml`, `validate.py` | Threat model catalog (`TM-NNN-*.md`), its controlled vocabulary and validator |
| `ansible/` | Playbooks that create, verify and destroy one SPE instance (`ansible/README.md`) |
| `agent/` | Pydantic AI pentest agent served over AG-UI |
| `chat-ui/` | Next.js + CopilotKit chat for the agent |
| `evals/` | promptfoo provider, assertions and starter suite against the agent |
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
(cd evals && uv run --group dev pytest -q)           # promptfoo provider and assertions
(cd chat-ui && npm ci && npm run build)              # chat UI (type check)
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

State (2026-10-15, second session):

- Done: Tasks 1–11, including their paid checks (smoke, two-turn chat, promptfoo 3/3); Task 12 step 1 (`instances/denbi.example.yml`); Task 13 spec reconciliation (spec §12).
- Pending, operator: the de.NBI target, its deployment and documentation (Task 12 steps 2–5).
- The dev VM runs `dev-local` with `spe_frontend: agui` (Anthropic `claude-haiku-5-5`, smoke off).

**To resume**, start a session in the worktree
`.claude/worktrees/agui-impl` (or a fresh checkout of the branch). Read the
progress file, then the plan, and continue at the first task not marked done.
The dev VM already runs the `dev-local` instance. Its private instance file
`ansible/instances/dev-local.yml` and its `ansible/output/dev-local/` exist
only in that worktree.
