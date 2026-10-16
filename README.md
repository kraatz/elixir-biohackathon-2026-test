# elixir-biohackathon-2026-test

Threat models for agents working inside Secure Processing Environments (SPEs), and
the Ansible automation that builds SPE evaluation instances: a GA4GH workflow stack
(WES, DRS, TRS) seeded with test data and canary tokens, plus an agent frontend to
probe it.

- **New here? Start with [`docs/getting-started.md`](docs/getting-started.md)**: an
  instance with the AG-UI agent on an existing VM, including every private value
  the setup needs and where it must (and must not) live.
- [`AGENTS.md`](AGENTS.md): repository layout, working rules, how to run the tests.
- [`ansible/README.md`](ansible/README.md): every playbook option.
- `agent/`, `chat-ui/`, `evals/`: the agent, its chat UI and its evaluations, each
  with its own README.
- `threats/`: the threat model catalog.
