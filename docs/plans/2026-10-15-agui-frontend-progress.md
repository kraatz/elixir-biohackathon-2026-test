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
| 3 SPE stack on the dev VM | done | full `create.yml`: `failed=0`, smoke `COMPLETE`; WES/TRS/DRS all `200` with `output/dev-local/ca.crt`. Re-run `changed` in `Whole stack up` was the one-shot `weskit-data-init` container being started again; fixed in `d62ef54` (stack re-run `changed=0`). `verify.yml` alone: `failed=0`, smoke `COMPLETE`. README note added |
| 4 Reset instead of delete | done | 18 reset-plan tests (35 preflight tests total); refused without confirmation, with mismatched `spe_provision`, with a path not in the manifest, with a mismatched instance (all `failed=1`, stack untouched); confirmed reset `failed=0`: marker, manifest, three directories, CA anchor, containers and project volumes gone, while `daemon.json`, other containers/volumes, images, the dummy dataset and `output/dev-local` were unchanged; re-create `failed=0`, smoke `COMPLETE` |
| 5 Shared `sandbox` role | done | Open WebUI templates render identically before/after (`diff -r` → SAME); `create.yml` syntax check clean. First real build of the role on the VM happens in Task 10 |
| 6 Agent package and config | done, `80b2ae9` | 7 tests |
| 7 Sandbox tools from OpenAPI | done | Adapter and provenance documented in `agent/README.md`; 50 sandbox tests plus 7 configuration tests pass offline; no paid calls |
| 8 Agent loop, AG-UI, run log, image | done | 90 offline agent tests (25 service, 15 config, 50 sandbox), also run in the image's `test` stage; image checks against a real open-terminal 0.12.4: 503 unready, 401 without/wrong key, 200 with 16 tools after the sandbox started and again after it restarted, Docker `healthy`, uid 10001, read-only root, `cap_drop ALL`, no keys in the logs. `claude-haiku-5-5` confirmed `active` via the free model-info endpoint; no paid calls |
| 9 CopilotKit chat | done | `next build` (type check) passes; headless Chromium against `dev/fake_agent.py` (real agent app, scripted model, fake sandbox): tool cards with arguments and results, second turn, run error in the alert bar; no test key in any of 18 responses or the HTML, no requests to non-local hosts. Same run against the image with a read-only root, uid 1000, `cap_drop ALL`: identical; Docker `healthy` |
| 10 Ansible `agui` role | done except paid checks | 10 smoke-helper tests (`dev/tests`: 50 pass). Dev VM with `anthropic`/`claude-haiku-5-5`, smoke off: create `failed=0`; second converge `failed=0` with no agui/sandbox/compose change and no container restart; `verify.yml` `failed=0` (health, UI, 401 ×2, key boundary through the sandbox API: no agent/LLM key in a command's env, sandbox→agent 401); ports only on 127.0.0.1; `daemon.json` unchanged; `agent_api_key` 0600, no key in `hosts.yml`/`summary.md`. Switched to Open WebUI and back with `--tags frontend`: only the selected stack runs, all three volumes kept. Open WebUI rendering still byte-identical. Paid checks done after the user's OK: smoke passed; two-turn chat with visible tool calls passed |
| 11 promptfoo client and evals | done except the paid run | promptfoo 0.124.1 `call_api(prompt, options, context)` interface read from its `persistent_wrapper.py`; Python assertions get `(output, context)` with `context.metadata` = provider metadata (from its assertion code). 18 offline tests (provider over synthetic SSE in 1–7-byte chunks, CRLF, multi-line data, UTF-8 splits, RUN_ERROR, truncation, malformed, 401, timeout, history; assertions). Whole suite run with promptfoo against `dev/fake_agent.py`: 3 runs, no errors, assertions evaluated on real metadata (content checks fail by design), no key in the report. Real-model suite: 3/3 passed (after fixing the provider timeout key, below) |
| 12 de.NBI deployment | step 1 done (`cc2d835`) | `instances/denbi.example.yml`. Steps 2–5 need the operator: target VM, replacement authorization if it is occupied, SSH through the jump host |
| 13 Reconcile | spec and docs done (`3a0f0ed`); knowledge record 0005 in the parent repository updated separately | Paid checks and de.NBI remain pending in the acceptance matrix |

## Acceptance evidence (2026-10-15)

| Outcome | State |
|---|---|
| Existing-VM lifecycle | met: create, converge, ownership refusal, confirmed reset and re-create, `daemon.json` unchanged |
| Baseline retained | met: Open WebUI rendering identical; shared sandbox builds; switching both ways keeps volumes |
| Agent behavior | met: 90 offline agent tests (schema, streaming, history, limits, readiness, logging, cancellation) |
| Credential boundary | met: 401s, no agent/LLM key in the sandbox env, sandbox→agent 401, no key in browser assets or responses, 0600 handoff, redacted logs |
| User experience | met: scripted agent (tool cards, second turn, visible errors) and real model (two-turn chat with tool cards) |
| Evaluation | met: offline tests, scripted-agent run, real-model suite 3/3 (`anthropic`, not comparable with de.NBI) |
| Deployment | dev VM met; **pending** de.NBI (operator) |
| Reproducibility | met: locks (`uv.lock` ×2, `package-lock.json` ×2), examples, docs, source commits recorded, no secrets staged |

Final review: self-review of the whole branch (this session spawns no subagents unless asked); no Critical or Important findings. Deferred minors:
- `dev/tests/__pycache__/` is not ignored by git (shows as untracked).
- After readiness, a sandbox outage is noticed within the 30 s probe interval; runs in that window get tool errors rather than 503.
- `spe_data`, `drs_register`, `trs_install` and handoff tasks still report `changed` on every converge (pre-existing).

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
- Task 3: the re-run `changed` in `Whole stack up` was the one-shot `weskit-data-init` container, started again by every `compose up`; `changed_when` now ignores actions on that container alone (`d62ef54`). Cost: a real change confined to that container goes unreported.
- Task 4: the reset guards live in `spe_preflight.py` as a `reset` mode (`reset_plan`), tested with a fake host, instead of inline assert tasks; it shares the path-safety helpers with the create preflight. Cost: one script with two modes.
- Task 4: a reset also refuses a path that is or holds a mount point, and, when the host is the controller, a path overlapping `spe_source_data_root` or `spe_output_root` (the dev VM's `spe_data_root` is `/data-share`, the default name of the shared GIAB dataset). Cost: a host whose instance directory is its own mount cannot be reset by the playbook.
- Task 4: OpenStack teardown still runs without a hand-off file (creation may have failed before writing it); only a hand-off that disagrees with the instance file refuses. Existing-VM resets require it. Cost: an OpenStack instance file pointed at the wrong cloud still deletes by name, as before.
- Task 4: `update-ca-certificates` without `--fresh`, and only when the anchor was removed: removing a file from `/usr/local/share/ca-certificates` is enough for it to drop the link, and `--fresh` would rebuild every other link on the host. Cost: none expected.
- Task 8: prompt order verified in Open WebUI v0.11.3 (`2a960a5`): model prompt, `\n`, terminal `/system` prompt. Client-sent system messages are stripped (`manage_system_prompt='server'`). Cost: none expected.
- Task 8: after readiness the agent probes the sandbox's `/openapi.json` every 30 s and drops to 503 when it fails, rediscovering with backoff (1 s doubling to 30 s). Cost: up to 30 s of 200 while the sandbox is down; runs then get tool errors, not 503.
- Task 8: the run log is built from the AG-UI events the client receives; a tool call's duration is measured from the end of its arguments to its result. Usage comes from `on_complete`, so failed and cancelled runs have no usage. Cost: durations include scheduling time; failed runs' spend is not recorded.
- Task 8: `RUN_ERROR` messages are redacted and cut to 500 characters; log fields are cut to 16384 bytes. Cost: long provider errors lose their tail.
- Task 8: `limits` and `tools.max_output_bytes` must be positive (`PositiveInt`); four parametrised config tests added to `test_config.py`. Cost: none.
- Task 8: `create_app(..., retry_delay, max_retry_delay, probe_interval)` keyword arguments beyond the plan's signature, for tests. Cost: none.
- Task 8: malformed AG-UI bodies get 422 with pydantic errors minus their input (Pydantic AI's `validation_error_response` is private in 2.56). Cost: none.
- Task 9: route shape is a catch-all `app/api/copilotkit/[[...slug]]/route.ts` with `createCopilotRuntimeHandler({ basePath: "/api/copilotkit" })` (multi-route mode), not the spec's single-file route. Cost: none; the client's `runtimeUrl` is `/api/copilotkit`.
- Task 9: Next.js `output: "standalone"`, run as `node server.js` instead of `next start`. Cost: the image must copy `.next/static` itself (done in the Dockerfile).
- Task 9: telemetry disabled (`NEXT_TELEMETRY_DISABLED`, `COPILOTKIT_TELEMETRY_DISABLED`, `DO_NOT_TRACK`): an SPE UI must not phone home. Cost: none.
- Task 9: TypeScript pinned to 6.0.3 (7.x has no JS API for `next build`'s type check). Cost: none.
- Task 9: `dev/fake_agent.py` added (not in the plan's file list): the real agent with a scripted model and fake sandbox, used for the UI checks and reusable by Task 10/11. Cost: one dev file.
- Task 10: build contexts are the git-tracked files under `agent/` and `chat-ui/`, staged on the controller with `git ls-files | rsync --files-from`, synced with `delete` and `checksum`; image tags are the first 12 hex of a sha256 over the staged files. Cost: uncommitted new files are not deployed.
- Task 10: bind-mounted `agent.yaml` and the prompt are hashed into a container label (`spe.agent-config`), so compose recreates the agent when only they change. Cost: none.
- Task 10: the shared checks (`roles/agui/tasks/checks.yml`) run at the end of the role without the smoke, and again in the verify role (also part of `create.yml`) with the smoke when `spe_agui_smoke`: one paid call per run, not two. Cost: checks run twice per create.
- Task 10: the key-boundary check runs `agui_probe.py` in the agent container, which asks the sandbox's own `/execute` API (with the sandbox key the agent holds) for `env` and an unauthenticated `curl` to the agent; the LLM key is compared from `agent.env` on the VM, so `verify.yml` needs no LLM key on the controller. Cost: none.
- Task 10: the openwebui role gained `remove_orphans: true`; without it, switching from agui left the agui containers running. Its rendered files are unchanged (diffed). Cost: none.
- Task 10: openwebui's admin signup now accepts 403 (`e1d1741`): Open WebUI v0.11.3 answers 403 once the admin exists, so its second converge failed (pre-existing). Cost: none; sign-in still verifies.
- Task 10: the switch test ran with `-e spe_min_free_gb=10` after the Open WebUI image pull left 14 GB free; that image was removed afterwards (22 GB free) and the final converge used the default 15. Docker's shared build cache was not pruned. Cost: none.
- Task 10: `spe_agent_base_url` (default `spe_llm_base_url`) and `spe_agent_include_sandbox_prompt` added beside the spec's variables. Cost: none.
- Task 11: the provider and assertions use only the standard library (`urllib`), so promptfoo's own Python runs them without a virtualenv; `pyproject.toml`/`uv.lock` pin only pytest for the offline tests, and `package.json`/`package-lock.json` pin promptfoo. Cost: none.
- Task 11: `metadata.usage` is absent: the AG-UI stream carries no token usage (the agent's run log records it). Cost: per-test spend must be read from the run log.
- Task 11: the starter suite has 3 tests (TLS and key checks apply to all through `defaultTest`). Cost: none.
- Task 11: the LLM key for `no_key_leak` comes from `SPE_LLM_API_KEY[_FILE]` on the controller; the check fails (rather than passing vacuously) when either key is missing. Cost: one more variable to set.

Real-model results (dev VM, `anthropic`/`claude-haiku-5-5`, 2026-10-15, approved by the user): the AG-UI smoke run through `verify.yml -e spe_agui_smoke=true` passed (`run_command`, `get_process_status`, `run_command`, `RUN_FINISHED`; `failed=0`); a two-turn chat in the browser showed 3 then 1 tool cards and answered the second turn from the first turn's history, no error, no key in any response; the promptfoo starter suite passed 3 of 3 with no key in the report. All 8 runs together: 27 model requests, 244,099 input and 5,035 output tokens (about $0.03 at the spec's prices).

- Task 11: promptfoo reads a Python provider's `config.timeout` as its worker timeout in milliseconds; the provider's own run deadline is now `config.run_timeout_s` (seconds) and the suite sets `timeout: 660000`. Found by the first real run, whose worker was killed after 0.6 s (one agent run cancelled). Cost: none.
- Paid checks: the per-run limits (50/100/400000) were left in place when the user lifted the approval gate; they can be raised with `spe_agent_*_limit`. Cost: a very long run ends in RUN_ERROR.
