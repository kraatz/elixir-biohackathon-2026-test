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
| `docs/getting-started.md` | Deploying and using an instance, and its private configuration |
| `docs/specs/`, `docs/plans/` | Design specs and implementation plans |

## Working rules

- **Commit each coherent change** with a short imperative subject, and add a body saying why when the subject doesn't. Run `git status` and `git diff --staged` first, and stage files by name rather than with `git add -A`.
- **Never commit secrets**: real instance files (`ansible/instances/*.yml` other than `example.yml` and `*.example.yml`, ignored by git) carry the seed that reproduces every canary. Also never commit `ansible/output/`, `canaries.json`, keys, `clouds.yaml` or `.env` files.
- **Push only as the last step of a unit of work** (below): a fast-forward of the working branch. Never rewrite history or force-push.
- **Paid model calls need the human's OK** before they run. On this repository's development VM the agent uses Anthropic with `claude-haiku-5-5`, pinned by `spe_agent_allowed_models` in that VM's instance file (a spend guard for that VM). Other setups choose their own provider and model.
- **Follow the plan's rulings discipline**: when work departs from a plan, record the decision, why, and its cost if wrong in that plan's progress file.

## Lifecycle of a unit of work

A unit of work is a coherent change: a fix, a feature, a docs update. Each is
done in its own worktree and ends on the working branch (`agent-agui-frontend`),
pushed, so the local branch and the remote always show the current state.

1. **Create a worktree from the local working branch**, not from `origin`, so it
   includes unpushed commits:
   `git worktree add <path> -b <topic> agent-agui-frontend`.
2. **Commit** in the worktree, as in the working rules above.
3. **Fast-forward the local working branch** to the work, in the main checkout:
   `git merge --ff-only <topic>`.
4. **Push it**: `git push origin agent-agui-frontend`, a fast-forward only. If the
   remote has moved on, fetch and rebase the local work, never force.
5. **Clean up the worktree**: `git worktree remove <path>` and
   `git branch -d <topic>`. Check first that it has no uncommitted changes.

Private instance files and `ansible/output/` exist only in the main checkout,
not in a worktree. To deploy a worktree's agent or chat UI before it is merged,
run Ansible from the main checkout with `-e spe_agui_source_dir=<worktree>`.

When this repository is a submodule (of `biohackathon`), the parent records the
pinned commit; move the pin there after the push.

## Running things

```bash
uv run --with pyyaml --with python-frontmatter python validate.py   # threat catalog
uv run --with pytest pytest dev/tests -q             # dataset generator, host preflight
(cd agent && uv run --group dev pytest -q)           # agent
(cd evals && uv run --group dev pytest -q)           # promptfoo provider and assertions
(cd chat-ui && npm ci && npm run build)              # chat UI (type check)
cd ansible && ansible-playbook playbooks/create.yml -e @instances/NAME.yml </dev/null
```

Ansible needs a blocking stdin here: always run it with `</dev/null`, from
`ansible/`. The collections come from the system Ansible package.

## AG-UI agent frontend

Built from plan `docs/plans/2026-10-15-agui-frontend.md` and spec
`docs/specs/2026-10-15-agui-frontend-design.md` (§12: what implementation verified
and changed) on branch `agent-agui-frontend`. The record of the work, every
deviation from the plan with its cost if wrong, and the acceptance evidence is
[`docs/plans/2026-10-15-agui-frontend-progress.md`](docs/plans/2026-10-15-agui-frontend-progress.md).
How to deploy and use it: [`docs/getting-started.md`](docs/getting-started.md).

All 13 tasks are done, including the model-backed checks on the development VM
(where this VM uses Anthropic `claude-haiku-5-5`) and on de.NBI (`qwen3.8-27b`). Running instances
(2026-10-16): `dev-local` on the development VM and `denbi-agui-01` on de.NBI
`agent-service-1` (converging there needs `-e spe_min_free_gb=5` until disk is
freed). Their private instance files and `ansible/output/` directories exist only
in the operator's checkout, never in git.
