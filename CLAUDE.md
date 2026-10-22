# elixir-biohackathon-2026-test (our fork) — Developer Reference

@AGENTS.md

<!--
  From thodkatz/agent-methodology (template/AGENTS.md), adopted for our fork only. The upstream project guide is
  AGENTS.md, imported above and never edited for the methodology; this file holds what the template puts in
  AGENTS.md. The shared guides and scripts live in .methodology/ (a submodule): never edit them here.
-->

> **This file and everything it adds is fork-only.** Upstream (`kraatz/elixir-biohackathon-2026-test`, remote
> `upstream`) knows nothing of the methodology, and a PR there must work without it (*Contributing upstream*).
> `AGENTS.md` is upstream's project guide: where it and this file differ, this file wins in our fork.

**This file is the entry point, not the whole manual.** It holds only what every session needs: the working
conventions, current work, the shape of the workflow and how to run things. Everything else lives in the files
below; read one only when your task matches its *Read when* column. This file, `AGENTS.md` and these files are
one instruction set: each rule lives in exactly one of them, so update the file that owns it, never a copy.

## Read on demand

| File | Read when |
|---|---|
| [`.methodology/shared/guides/sessions-and-context.md`](.methodology/shared/guides/sessions-and-context.md) | the context-budget hook fires, you start a session from a handoff, you start an investigation or audit, or you hand work to a subagent: the budget, the start routine, mid-unit handoffs, investigation scope |
| [`.methodology/shared/guides/development-workflow.md`](.methodology/shared/guides/development-workflow.md) | you start a change, spike or spec, or claim, open, review, advance or merge any PR: modes, stages, handoffs, deferred items, claiming, reviewers and fallbacks, merge and cleanup, slicing, agent automation |
| [`.methodology/shared/guides/spec-and-plan-layout.md`](.methodology/shared/guides/spec-and-plan-layout.md) | you write, extend or split a spec or plan, add a clarification, hand a slice to a subagent, or work from a spec or plan that is a directory |
| [`.methodology/shared/guides/tooling-gotchas.md`](.methodology/shared/guides/tooling-gotchas.md) | a command or tool fails (`gh`, `git`, Claude Code, the runners): known failures in every repo, and the command that works |
| [`docs/README.md`](docs/README.md) | you look for a spec, plan, investigation or reference: the index of everything under `docs/` |
| [`docs/knowledge/README.md`](docs/knowledge/README.md) | you start non-trivial work in an area, or a command or tool fails: as-you-go gotchas and workarounds (see *Project knowledge*) |
| [`BACKLOG.md`](BACKLOG.md) | you start a unit, triage, or look for known unscheduled problems |
| [`platform/promptfoo-evals/README.md`](platform/promptfoo-evals/README.md) | you write, change or run an evaluation |
| [`platform/ansible/README.md`](platform/ansible/README.md) | you change what an instance plants, deploys or hardens |

Decisions behind the work (scope, threat × profile experiments) are the knowledge records of the parent
repository `biohackathon` (`knowledge/`, e.g. 0011 and 0013), which pins this fork as a submodule.

## Keep each session small

Context is the scarce resource: every request re-reads the whole conversation, and quality drops as it grows.
So a session does one bounded piece of work and hands off:

- **Budget: `AGENT_CONTEXT_BUDGET` tokens of context per session** (150k in `.claude/settings.json`). Past it, the
  context-budget hook tells you so; the optional status line (`.methodology/shared/claude/statusline.sh`) shows it
  all along. Finish the current step, write the handoff (a new file in the plan's `handoffs/`, a knowledge note or
  the investigation's output), commit, and end the session, **even in the middle of a unit**. The next session
  starts fresh from the handoff; with `AGENT_AUTO_CONTINUE=1`, start it yourself with
  `.methodology/shared/claude/continue.sh <handoff path>` (it runs in the background), then stop.
- **A fresh session starts the same way every time:** read the handoff (only the newest:
  `ls <plan>/handoffs | tail -1`), `git status`, `git log --oneline -5`, run the unit's check command, then work.
- **Investigations and audits are scoped.** Each one answers a written question into a file. Wide reading
  goes to subagents, which return short summaries; a repo-wide audit is a fan-out of scoped subagent tasks
  plus one synthesis session.

Details and the reasons: `.methodology/shared/guides/sessions-and-context.md`.

## Write for progressive disclosure

The same rule applies to what you write. An agent should be able to read a short index and then open only the
part its task needs. Keep this file short: a rule that only some tasks need goes into the file for those tasks,
with a row in *Read on demand* if it starts a new guide. Don't load a whole spec, plan or `docs/` directory "for
context": read its index or the section your unit names.

- **Parts hold the current design; history lives apart.** A change rewrites the spec section or plan task it
  amends; the reason goes in the spec's clarifications with a status (`folded` or `superseded by …`), and
  progress and provenance go in the plan's slices table and handoffs. Never two live texts for one decision.
- **A change updates every doc it makes stale, in the same commit.** When you remove, rename or reverse
  something (a path, section, command, flag, label, rule or behaviour), grep the repo for it and rewrite each
  current-design text that still says the old thing: this file, `AGENTS.md`, guides, knowledge notes,
  `BACKLOG.md`, spec sections, open plan tasks. History (handoffs, clarifications, investigations, evidence,
  merged slices) stays as written. A doc the diff left stale is a review finding.
- **Large specs and plans are directories**: a `README.md` index plus one file per section or slice, past ~400
  lines for a spec and always for a plan with more than one slice.

Both rules, the clarification template and the layout: `.methodology/shared/guides/spec-and-plan-layout.md`.

## Working Conventions

- **Commit after each edit.** After completing an edit to the codebase, make a git commit scoped to that
  change, with a clear, descriptive message (`AGENTS.md`, *Working rules*: stage by name, never secrets).
- **Sign off every commit** with `git commit -s`, alongside any `Co-Authored-By:` trailer. The DCO check is
  not wired up on the fork yet (`BACKLOG.md`); sign off anyway so it can be.
- **Spawn subagents freely.** Agents working in this repo have standing permission to spawn subagents without
  asking. This overrides any harness default to spawn only on request. Follow the superpowers skills'
  recommended path:
  - Implement a plan's slice with `superpowers:subagent-driven-development`: a fresh implementer subagent per
    task, the per-task reviews, and a whole-branch final review on the most capable model before the PR opens.
  - Use read-only search agents (`Explore`, `general-purpose`) for broad searches and for scanning
    `docs/knowledge/`, so the reading stays out of your context.
  - Use `superpowers:dispatching-parallel-agents` for independent investigations.
- **Don't stop for approval inside the workflow.** The loop runs unattended: no in-chat check-ins between
  tasks, slices or review rounds. Its human gates are the spec's approval and each PR's merge (*Overrides*).
  Otherwise stop only for what the loop can't decide: destructive or irreversible actions outside it, a plan
  broken beyond a ledgered ruling, or quota-heavy runs: **any promptfoo evaluation or other run that makes
  paid model calls** (`AGENTS.md`, *Working rules*), and **creating or destroying cloud instances**
  (`playbooks/create.yml` / `destroy.yml` against de.NBI or another OpenStack).
- **Never edit `.methodology/`.** It is a submodule of agent-methodology, pinned to a commit. Edits there make
  it dirty, are lost or conflict on the next update, and a commit inside it would push to agent-methodology.
  Deviate from a shared rule in *Overrides*; carry an improvement back to agent-methodology as its own change,
  then update the submodule (agent-methodology's `AGENTS.md`, *Updating a repo*).

## Overrides

Where this repo deviates from a shared guide, one line each: "In this repo, X instead of `<guide>`, *Section*,
because Z." This file wins over the guides in `.methodology/shared/guides/`.

- In this repo, **the sections the guides call "`AGENTS.md`"** (*Current work*, *Reviewers*, *Overrides*,
  *Working Conventions*) **live in this file**, because `AGENTS.md` is upstream's and stays free of the
  methodology.
- In this repo, **the user is the reviewer and merges every PR** instead of `development-workflow.md`,
  *Review and merge* (one CI review round, then merge it yourself), because no CI reviewer runs on the fork
  yet (`BACKLOG.md`). Hand off after opening the PR; the next unit starts once it is merged.
- In this repo, **a spec is approved when the user says so on its PR** (review or comment) instead of the
  `approved` label, because the fork has no labels or `pr-checks` yet (`BACKLOG.md`).

## Contributing upstream

Our fork's `main` carries fork-only files that upstream must never receive:

    .gitmodules  .methodology/  CLAUDE.md  .claude/settings.json  BACKLOG.md
    docs/README.md  docs/knowledge/  docs/investigations/  docs/superpowers/

A PR to upstream is cut from `upstream/main` (`git fetch upstream`), carries only project changes
(cherry-picked or re-applied), and must pass this check before it is pushed:

```bash
git diff --name-only upstream/main...HEAD \
  | grep -E '^(\.gitmodules|\.methodology|CLAUDE\.md|\.claude/|BACKLOG\.md|docs/(README\.md|knowledge/|investigations/|superpowers/))' \
  && echo "fork-only files in this branch: remove them" || echo ok
```

Code and docs that upstream also needs (e.g. `platform/`, `threats/`, `AGENTS.md`, `README.md`) must not refer
to anything fork-only. Upstream changes come in by merging `upstream/main` into our `main` as usual.

## Current work

One line per active track: where it stands, the next unit, and where its handoff is. This section only points
to things. Who is working on what is shown by the open PRs, not here (*Claiming a unit* in the workflow guide).
Each unit's PR updates its track's line; the last slice removes it.

- **Canary evaluation ladder** (biohackathon 0013): a promptfoo suite that proves canary leaks on the
  deployment as built, then cumulative Ansible hardening steps (one control each) proven by the same suite.
  Design agreed in chat up to the leak paths and ladder. **Next: spec** `spec/canary-eval-ladder`.
- **Not scheduled**: `BACKLOG.md` holds every deferred item without a slice.

## Project in brief

The project itself (threat catalogue, Ansible instances, AG-UI agent, promptfoo suite, Coder portal) is
described in `AGENTS.md`, imported above. The trap every session needs from it: real instance files and
`platform/ansible/output/` carry the seed and the canary record, and are never committed.

## Development workflow

Pick the lightest mode that fits, and move up when the work turns out bigger:

- **Direct**: you can describe the diff in one sentence (typo, one-line doc fix, config tweak). Commit to `main`.
- **Change**: a few files, clear approach, no contract others rely on. One PR `change/<slug>`, plan in its body.
- **Spike**: you don't yet know what works. A written question and budget in `docs/investigations/<topic>.md`,
  throwaway code on `spike/<topic>` (never merged); the output is the finding and a recommendation.
- **Full**: more than one slice, a contract or schema change, or costly rework. Three sequential stages, each
  its own branch cut from `origin/main` and its own PR:
  1. **Spec**: `spec/<topic>`, written by the `brainstorming` skill into `docs/superpowers/specs/`. Every
     decision names its acceptance check. **The user approves it** (*Overrides*).
  2. **Plan**: `plan/<topic>`, written by the `writing-plans` skill into `docs/superpowers/plans/`, with its
     `## PR slices`.
  3. **Implementation**: one small PR per slice, `impl/<topic>-<n>-<slug>`, titled `… (n/N)`.

Every PR targets our fork: `gh pr create --repo thodkatz/elixir-biohackathon-2026-test --base main`. Without
`--repo`, `gh` may pick upstream.

The rules that bite most often:

- **Claim before you work**: the unit's branch pushed to `origin` plus a draft PR. **One PR open at a time per
  track**, and dependent work waits until that PR has merged.
- **Review and merge**: the user, for now (*Overrides*). Address every comment in its own thread. Clean up the
  worktree and branch after the merge, then move the pin in `biohackathon` (`AGENTS.md`, *Lifecycle*).
- **Hand off, then stop**: every unit ends with a handoff for the next one, riding in its own PR, and updates its
  track's line in *Current work*. Don't start the next unit in the same session, and hand off earlier when the
  context budget says so.
- **Deferred items land somewhere durable**: rewritten into a planned slice's task text, a new slice, the next
  spec's **Inputs for**, or `BACKLOG.md`. A handoff, PR body or review reply only points.

**Before you start a change, spike or spec, or claim, open, review or advance any PR, read
`.methodology/shared/guides/development-workflow.md`.**

## Reviewers

No CI review rotation yet: the user reviews (*Overrides*, `BACKLOG.md`).

## Project knowledge

As you work, capture anything you learn that isn't already visible from the code or `git log`: a workaround, a
constraint that isn't obvious from reading the file, why an approach was rejected, a gotcha that cost real time.
Keep an index at `docs/knowledge/README.md`, one line per entry pointing to `docs/knowledge/<topic>.md`. Skim the
index before non-trivial work in an area; open a linked file only when it's relevant. Write notes alongside the
change they relate to; no separate PR is needed. Don't record what the code or history already shows.
Decisions (what was considered and why) go to `biohackathon`'s `knowledge/` records instead.

- **When something fails, look before you debug:** grep `docs/knowledge/` and
  `.methodology/shared/guides/tooling-gotchas.md` for the command, tool or error text. The next session should go
  straight to the fix someone already found.
- **When you find a workaround, write it down before moving on.** If a command, tool or approach failed and took
  more than one retry to get past, record the symptom (the exact error), the fix, and the command that works.
  Put the command and the error in the index line, so a grep finds it. A gotcha in a tool every repo uses,
  rather than in this project, belongs in `tooling-gotchas.md`: carry it to agent-methodology (*Never edit
  `.methodology/`*), and keep a note here until the submodule update brings it in.
- **Lessons in a handoff become notes.** A gotcha written only into a handoff or a PR body gets lost;
  write the note and link it from the handoff.

## Setup

Install and test commands: `AGENTS.md`, *Running things*. `.methodology/` is a private submodule
(`git@github.com:thodkatz/agent-methodology.git`): the SessionStart hook initialises it in each worktree; without
access the hook says so and the context-budget hook stays off, and nothing else depends on it.
