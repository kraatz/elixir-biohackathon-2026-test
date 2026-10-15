# AG-UI frontend: implementation progress and handoff

Plan: `docs/plans/2026-10-15-agui-frontend.md`. Spec: `docs/specs/2026-10-15-agui-frontend-design.md`.
Branch `agent-agui-frontend-impl`, cut from `agent-agui-frontend` at `c5960c6`
(that branch is checked out in the main working copy, so the work lives on its own
branch; fast-forward `agent-agui-frontend` to it when accepted). Nothing is pushed.

A new session picks up from here: read this file, then the plan, then continue
at the first task not marked done.

## State

| Task | State | Evidence |
|---|---|---|
| 1 Existing-host provisioning | done, `dec71fa` | 17 preflight tests; `base` on the dev VM left `daemon.json` unchanged; another instance refused (`failed=1`); re-run `changed=0` |
| 2 Dummy dataset | done, `9d45036` | 5 tests; dataset in `/home/agentvm/spe-dummy-data` (seed 1, 1.4 MB) |
| 3 SPE stack on the dev VM | steps 1–4 run; 5–6 open | full `create.yml`: `failed=0`, smoke `COMPLETE`; WES/TRS/DRS all `200` with `output/dev-local/ca.crt`. Re-run: `failed=0`, `changed=7`, **but `workflow_stack : Whole stack up` reported changed** (plan expects only `Seed instance data`). Not yet debugged: Task 1 did not touch `workflow_stack`, so probably existing behaviour; check before calling step 4 met. Also changed: `drs_register`, `trs_install`, `spe_data` ownership, two handoff files. Open: `verify.yml` (step 5), README note (step 6) |
| 4 Reset instead of delete | not started | |
| 5 Shared `sandbox` role | not started | |
| 6 Agent package and config | done, `80b2ae9` | 7 tests |
| 7 Sandbox tools from OpenAPI | done | Adapter and provenance documented in `agent/README.md`; 50 sandbox tests plus 7 configuration tests pass offline; no paid calls |
| 8–13 | not started | |

No paid model calls have been made. Each step that makes paid calls still needs the human's OK first.

## Local, not in git

- `ansible/instances/dev-local.yml` (mode 0600): the dev instance file with a fresh seed. Never commit it.
- `ansible/output/dev-local/`: hand-off, CA, canary record. Ignored by git.
- On the VM: `/etc/spe-instance`, `/etc/spe-instance.json`, `/home/ubuntu/workflow-stack`, `/data-share`, the `workflow-stack` compose project.

## Environment notes

- Run `ansible-playbook` with `</dev/null` (it needs a blocking stdin), from `ansible/`.
- Collections come from the system Ansible package; `ansible/collections/` is not needed.
- `~/.config/spe-dev/llm.env` (0600) holds the Anthropic key for later paid steps.
- Open WebUI v0.11.3 parity source: `backend/open_webui/utils/tools.py` (`convert_openapi_to_tool_payload`,
  `clean_properties`, `execute_tool_server`, `get_terminal_cwd`, `get_terminal_system_prompt`,
  `get_terminal_tools`). Notable: for POST/PUT/PATCH/DELETE with a request body, the JSON body is all arguments;
  DELETE without a body sends `{}`; HTTP >= 400 becomes `{"error": "HTTP error <status>: <text>"}`;
  it sends `X-Session-Id` = chat id.

## Rulings (deviations from the plan, with cost if wrong)

- Setup: branch `agent-agui-frontend-impl` instead of `agent-agui-frontend`; the main working copy holds that branch. Cost: one fast-forward.
- Spec says `spe_agui_smoke: true`; the plan says `false`. Chose `false` (paid calls need an OK; reconcile the spec in Task 13). Cost: the checks skip the smoke run by default.
- Task 1: the preflight is `ansible/roles/existing_host/files/spe_preflight.py` (stdlib, runs on the host, tested in `dev/tests/test_spe_preflight.py`), not inline assert tasks, because the plan's path, port, project, manifest and disk checks can't be tested in inline YAML. Cost: one extra file.
- Task 1: the ownership manifest is `/etc/spe-instance.json` (instance, provision mode, resolved paths, compose projects `workflow-stack` and `spe-frontend`), next to the plain-name marker `/etc/spe-instance`. Task 4's reset should read it. Cost: a path rename.
- Task 1: the IPv4 address is checked with Python's `ipaddress` on the controller (`ansible.utils.ipv4` needs netaddr). Cost: none.
- Task 1: `hosts.yml` is serialised with `to_nice_yaml`. Tunnels use one `spe_ssh_prefix` built from the recorded connection fields, and it is empty on the controller itself. Cost: the key order in `hosts.yml` changed.
- Task 7: the fixture comes from `ghcr.io/open-webui/open-terminal:0.12.4` @ `sha256:ca1d60e70f4eca35db62b80b128fffc7d7c156298167aac25cc4982947bcea5b`. Its 16 operation ids match the spec; `/openapi.json` needs no auth, `/execute` does.
- Task 7 (encoded in the tests): non-JSON responses are decoded as UTF-8 with replacement, not base64 data URIs as in Open WebUI. Cost: binary output differs from the baseline.
- Task 7: display_file's Open WebUI-only `inline`/`page` parameters are not added. Cost: one schema differs from the baseline.
- Task 7: 3xx responses are returned as an error result and not followed. Cost: none expected.
- Task 7: `build_tools(..., cwd=...)` and `SandboxClient.call(..., session_id=...)` (AG-UI thread id sent as `X-Session-Id`) go beyond the plan's signatures. Cost: two extra keyword arguments.
- Task 7: responses are streamed, at most 1 MiB is kept and the total is counted for the marker; a tool result, marker included, is at most `max_output_bytes`.

## Task 7 completion (2026-10-15)

Implemented only Task 7 on resumption, as requested. Verified the installed
Pydantic AI 2.56.0 `Tool.from_schema` API, implemented discovery and tool calls,
and expanded the handoff tests for encoded paths, injected-client auth/redirect
settings, malformed discovery, credential redaction and small output caps.
`uv run --group dev pytest -q` in `agent/`: 57 passed. Tasks 3–5 and 8–13
remain at their earlier status; stop here.

Additional Task 7 rulings: a 30-second total deadline bounds response counting
as well as per-I/O timeouts; responses exceeding that deadline return a timeout
error. Cost: very long streaming responses do not yield partial output. Tiny
output caps return a partial marker when a complete marker cannot fit. Cost:
those markers are not machine-parseable. Sandbox credentials are redacted from
response text. Cost: an intentional sandbox-key probe differs from the baseline.
