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
- **Do not push**, rewrite history or force anything unless asked. Pushing is the repository owner's call.
- **Paid model calls need the human's OK** before they run. On this repository's development VM the agent uses Anthropic with `claude-haiku-5-5` (a spend choice for that VM; with `anthropic` the agent currently accepts only that model, see `agent/README.md`). Other setups choose their own provider and model.
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
