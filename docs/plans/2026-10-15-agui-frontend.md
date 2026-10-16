# AG-UI Agent and CopilotKit Frontend Implementation Plan

> **Status:** Implementation plan, ready for review. All checkboxes describe future work; none indicate work performed while writing this document. Follow repository instructions and implement in task order. No additional skill or delegation is required.
>
> **Implementation (2026-10-15):** Tasks 1–11 implemented on `agent-agui-frontend-impl`; Task 12 step 1 done, steps 2–5 await the operator; Task 13 reconciled the spec (§12). Paid checks (smoke, two-turn chat, promptfoo suite) await approval. The checkboxes below are left as written; the record is `2026-10-15-agui-frontend-progress.md`.

**Goal:** An SPE instance on an existing VM runs a Pydantic AI agent we own, served over AG-UI, with a minimal CopilotKit chat in front and the existing open-terminal image as its sandbox, selected with `spe_frontend: agui` — first on the development VM, then on a de.NBI VM.

**Architecture:** `create.yml` gains `spe_provision: existing` (register a VM instead of creating it) and a dummy dataset replaces the GIAB genomes. A new `agui` role runs three containers in compose project `spe-frontend`: `sandbox` (open-terminal, unchanged image, built by a new shared `sandbox` role), `agent` (FastAPI + `AGUIAdapter`; tools generated from open-terminal's OpenAPI exactly as Open WebUI does; the only holder of the LLM key) and `chat-ui` (Next.js + CopilotKit v2, thin client). promptfoo calls the agent's AG-UI endpoint directly.

**Candidate versions (verify availability and API compatibility before locking in Tasks 6, 8, 9 and 11; these are inherited draft pins, not newly verified facts):** Ansible (ansible-core 2.21, community.docker, ansible.posix, community.crypto), Python 3.13 image / 3.14 dev (pydantic-ai-slim 2.56.0 with ag-ui/anthropic/openai extras, FastAPI 0.143.2, uvicorn 0.54.0, httpx 0.28.1, PyYAML 6.0.3, pytest), Node 24 (Next.js 16.4.1, React 19.3.1, @copilotkit/react-core and @copilotkit/runtime 1.79.0, @ag-ui/client 1.0.2), promptfoo 0.124.1, samtools/bcftools/htslib.

**Spec:** `docs/specs/2026-10-15-agui-frontend-design.md` (same branch). Background: knowledge record 0005 in the biohackathon repository.

## Global Constraints

- Repository: `elixir-biohackathon-2026-test`, branch `agent-agui-frontend`. Commit after each coherent task. Check `git status` and `git diff --staged` before committing; use accurate authorship. Stage files by name. Do not push.
- Never commit secrets: no seeds in real instance files, no keys, no `canaries.json`, no `output/`. Real instance files stay untracked; only `*.example.yml` are committed.
- `spe_frontend: openwebui` must keep producing the same rendered compose and env files as before.
- The process holding the LLM key and the place where model-chosen commands run are different containers.
- The agent rejects requests without `Authorization: Bearer <spe_agent_api_key>`; the sandbox never has that key; the chat UI never sends it to the browser.
- Anthropic provider: only `claude-haiku-5-5` is accepted. Every step that makes paid model calls says so and waits for the human's OK before running.
- Per-run limits: `request_limit` 50, `tool_calls_limit` 100, `total_tokens_limit` 400000 (added to the spec in Task 13, from the spend concern); tool output cut to 16384 bytes with the marker `[truncated: N of M bytes shown]`.
- Ports on the VM: chat UI `127.0.0.1:3000`, agent `127.0.0.1:8100`; sandbox publishes nothing.
- Previously observed development VM facts (recheck before use; paths and addresses are not portable): Ubuntu 26.04, no systemd, Docker 29.8 managed by agentvm with `data-root: /storage/docker` (must not be touched), passwordless sudo, own IP `100.96.0.2` (`hostname -I | cut -d' ' -f1`), user `ubuntu` (uid 1000, also named `agentvm`; `$HOME=/home/agentvm`).
- Ansible in this environment needs a blocking stdin: use `</dev/null`. For every piped command below, enable Bash `set -o pipefail`; require both exit status zero and a recap with `failed=0`, `unreachable=0`. Keep logs private and do not print secret-bearing tasks.
- SSH to de.NBI from the development VM only with `-F /home/agentvm/.ssh/config` (the system config adds a key the jump host rejects, and failed logins ban the IP). One attempt at a time; stop at the first failure.

## Planning baseline

Completed against test-repository commit `5a7fe53` on `agent-agui-frontend`.
The environment observations and external API parity notes below were inherited
from the draft/spec; this documentation pass inspected local playbooks and did
not repeat remote inspection or verify external package releases.

## Review Focus

1. **Sandbox not up yet, or restarted** — the agent must start anyway, answer `/healthz` and `/agent` with 503 until it can read the sandbox's OpenAPI, then work without a restart. Test in Task 8 (`test_unready_sandbox_gives_503_then_recovers`).
2. **Huge or binary tool output** (`cat` of a CRAM, a 10 MB log) — cut to the byte cap with the marker, never a crash on invalid UTF-8. Test in Task 7 (`test_binary_output_is_truncated_safely`).
3. **Odd arguments from the model** — an empty string for an optional query parameter, a path parameter containing `/` or `..` — empty optional values are dropped and path values are URL-encoded, so the model cannot address another route. Tests in Task 7 (`test_empty_optional_query_is_dropped`, `test_path_param_is_encoded`).
4. **Re-running against a host that is already in use** — the same instance converges; a different instance, or an unmarked stack in `spe_stack_dir`, or something else on port 443, is refused before anything changes. Tests in Task 1 (negative run) and Task 3 (idempotent re-run).
5. **Second turn of a conversation** — the client resends history containing an earlier tool call and its result; the run must continue normally. Test in Task 8 (`test_second_turn_with_tool_history`).

---

## File Structure

```
ansible/
  .gitignore                                   modify: ignore real instance files
  README.md                                    modify: existing hosts, dev VM, reset, agent frontend, evals
  inventory/group_vars/all.yml                 modify: provisioning, docker guard, agent/agui variables
  instances/dev-local.example.yml              create: development VM instance template
  instances/denbi.example.yml                  create: de.NBI existing-VM template (Task 12)
  playbooks/create.yml                         modify: provisioning switch, existing-host pre-checks
  playbooks/verify.yml                         modify: connect from hosts.yml; agui checks
  playbooks/destroy.yml                        modify: reset instead of delete for existing hosts
  roles/existing_host/tasks/main.yml           create: assert + add_host for an existing VM
  roles/base/tasks/main.yml                    modify: ownership marker, spe_manage_docker guard
  roles/spe_data/tasks/main.yml                modify: use_ssh_args on synchronize
  roles/handoff/tasks/main.yml                 modify: provision/ssh fields, frontend generalised
  roles/handoff/templates/summary.md.j2        modify: existing-host note, agui section
  roles/sandbox/                               create: build of the open-terminal image (moved from openwebui)
    tasks/main.yml
    files/{Dockerfile.terminal,AGENTS.md,system_prompt.txt}
  roles/openwebui/tasks/main.yml               modify: include sandbox role, prompt path
  roles/agui/                                  create: agent + chat-ui + sandbox compose project
    tasks/main.yml
    templates/{docker-compose.yml.j2,agent.yaml.j2,agent.env.j2,chat-ui.env.j2}
    files/agui_smoke.py
dev/
  make_dummy_dataset.py                        create: synthetic base dataset
  tests/test_make_dummy_dataset.py             create
agent/
  pyproject.toml, uv.lock, Dockerfile, .dockerignore, README.md
  src/spe_agent/{__init__,__main__,config,sandbox,agent,app,runlog}.py
  tests/{conftest.py,test_config.py,test_sandbox.py,test_app.py}
  tests/fixtures/open-terminal-0.12.4-openapi.json
chat-ui/
  package.json, package-lock.json, next.config.mjs, tsconfig.json, Dockerfile, .dockerignore
  app/{layout.tsx,page.tsx}
  app/api/copilotkit/[[...slug]]/route.ts
evals/
  agui_provider.py, asserts.py, promptfooconfig.yaml, README.md
  tests/test_agui_provider.py
docs/specs/2026-10-15-agui-frontend-design.md  modify (Task 13): record findings
```

---

## Phase A — An SPE on an existing VM

### Task 1: Existing-host provisioning, Docker guard, ownership marker

**Files:**
- Modify: `ansible/inventory/group_vars/all.yml` (new section after `# --- OpenStack ---`)
- Create: `ansible/roles/existing_host/tasks/main.yml`
- Modify: `ansible/playbooks/create.yml`
- Modify: `ansible/roles/base/tasks/main.yml`
- Modify: `ansible/roles/spe_data/tasks/main.yml` (two `synchronize` tasks)
- Modify: `ansible/roles/handoff/tasks/main.yml` (`Connection details` task), `ansible/roles/handoff/templates/summary.md.j2`
- Modify: `ansible/playbooks/verify.yml`
- Modify: `ansible/.gitignore`
- Create: `ansible/instances/dev-local.example.yml`
- Modify: `ansible/README.md`

**Interfaces:**
- Produces variables: `spe_provision` (`openstack|existing`), `spe_existing_host`, `spe_existing_api_ip`, `spe_existing_ssh_key`, `spe_existing_ssh_args`, `spe_manage_docker`, `spe_min_free_gb`.
- Produces `/etc/spe-instance` on the VM containing the instance name, and `hosts.yml` keys `provision`, `ssh_target`, `ssh_key`, `ssh_args`, `frontend`.

- [ ] **Step 1: Variables.** Add to `ansible/inventory/group_vars/all.yml` directly after the OpenStack block:

```yaml
# --- provisioning -------------------------------------------------------------
# openstack: create the VM (keypair, security group, server, floating IP).
# existing:  configure a VM that already exists; nothing in OpenStack is touched.
spe_provision: openstack
spe_existing_host: null       # existing: SSH target (alias from ~/.ssh/config or address), or localhost
spe_existing_api_ip: null     # existing: the VM's own IP; becomes spe_api_host (certificate IP SAN)
spe_existing_ssh_key: null    # existing: private key on the controller; null lets the ssh config decide
spe_existing_ssh_args: ""     # existing: extra ssh args, e.g. "-F /home/agentvm/.ssh/config"
spe_min_free_gb: 15           # existing: refuse a host with less free disk on /
spe_manage_docker: true       # false: Docker belongs to someone else on this host; base leaves it alone
```

- [ ] **Step 2: `existing_host` role.** Create `ansible/roles/existing_host/tasks/main.yml`:

```yaml
---
# Runs on the controller: register a VM that already exists instead of
# creating one. Nothing in OpenStack is touched.
- name: Existing-host parameters present
  ansible.builtin.assert:
    that:
      - spe_existing_host is string and spe_existing_host | length > 0
      - spe_existing_api_ip is string and spe_existing_api_ip is match('^[0-9]{1,3}(\.[0-9]{1,3}){3}$')
    fail_msg: >-
      spe_provision is 'existing': set spe_existing_host (SSH target or localhost)
      and spe_existing_api_ip (the VM's own IPv4 address) in the instance file.

- name: Output directory
  ansible.builtin.file:
    path: "{{ spe_output_dir }}"
    state: directory
    mode: "0700"

- name: Register the existing host
  ansible.builtin.add_host:
    name: "{{ spe_instance }}-api"
    groups: spe_api
    ansible_host: "{{ spe_existing_host }}"
    ansible_connection: "{{ 'local' if spe_existing_host in ['localhost', '127.0.0.1'] else 'ssh' }}"
    ansible_user: "{{ spe_ssh_user }}"
    ansible_ssh_private_key_file: "{{ spe_existing_ssh_key | default(omit, true) }}"
    ansible_ssh_common_args: "{{ spe_existing_ssh_args }}"
    ansible_python_interpreter: /usr/bin/python3
    spe_api_host: "{{ spe_existing_api_ip }}"
    spe_floating_ip: ""
  changed_when: false
```

- [ ] **Step 3: `create.yml`.** In play 1 replace the `roles:` list and add a provisioning assert to `pre_tasks`:

```yaml
  pre_tasks:
    - name: Instance parameters present
      ansible.builtin.assert:
        that:
          - spe_instance is string and spe_instance | length > 0
          - spe_seed is not none
          - spe_provision in ['openstack', 'existing']
        fail_msg: "set spe_instance and spe_seed (pass -e @instances/<name>.yml); spe_provision is openstack or existing"
  roles:
    - { role: os_provision, tags: [always], when: spe_provision == 'openstack' }
    - { role: existing_host, tags: [always], when: spe_provision == 'existing' }
```

In play 2, append to `pre_tasks` after `Wait for cloud-init` (before `Deterministic service-info tokens`):

```yaml
    - name: Existing host is fit and free for this instance
      tags: [always]
      when: spe_provision == 'existing'
      block:
        - name: Passwordless sudo
          ansible.builtin.command: sudo -n true
          changed_when: false
        - name: Ownership marker
          ansible.builtin.slurp:
            src: /etc/spe-instance
          register: spe_marker
          failed_when: false
        - name: Owner named in the marker
          ansible.builtin.set_fact:
            spe_marker_owner: "{{ (spe_marker.content | b64decode | trim) if spe_marker.content is defined else '' }}"
        - name: Refuse a host that belongs to another instance
          ansible.builtin.assert:
            that: spe_marker_owner in ['', spe_instance]
            fail_msg: "{{ inventory_hostname }} belongs to instance '{{ spe_marker_owner }}', not '{{ spe_instance }}'"
        - name: Stack directory
          ansible.builtin.stat:
            path: "{{ spe_stack_dir }}"
          register: spe_stack_dir_state
        - name: Something listening on 443
          ansible.builtin.shell: ss -Htln 'sport = :443' | wc -l
          register: spe_port_443
          changed_when: false
        - name: Refuse to take over an unmarked host
          ansible.builtin.assert:
            that:
              - spe_marker_owner == spe_instance or not spe_stack_dir_state.stat.exists
              - spe_marker_owner == spe_instance or (spe_port_443.stdout | int) == 0
            fail_msg: >-
              No /etc/spe-instance for {{ spe_instance }}, but {{ spe_stack_dir }} exists or port 443 is in use:
              another stack lives here. Pick another host or another spe_stack_dir.
        - name: Free disk on /
          ansible.builtin.shell: df -BG --output=avail / | tail -1 | tr -dc 0-9
          register: spe_free_gb
          changed_when: false
        - name: Enough disk
          ansible.builtin.assert:
            that: (spe_free_gb.stdout | int) >= spe_min_free_gb
            fail_msg: "only {{ spe_free_gb.stdout }} GB free on /, need {{ spe_min_free_gb }}"
```

Before any role mutates the existing host, extend this preflight to inspect
`spe_frontend_dir`, `spe_data_root`, all requested frontend ports and Compose
project ownership, as well as the stack directory/443 shown above. A matching
instance marker alone must not excuse an unrelated listener or directory.
Persist an ownership manifest containing the instance's resolved absolute paths
and Compose project names. Reject occupied unowned paths; never adopt them
implicitly. Check free space on the filesystems containing data and Docker's
actual data root, not only `/`. Validate the address with an IPv4 parser rather
than relying solely on the illustrative regex. Use the same checks for tagged
runs before writing the ownership marker.

- [ ] **Step 4: `base` role.** In `ansible/roles/base/tasks/main.yml`:
  - Insert as the first task:

```yaml
- name: Instance ownership marker
  ansible.builtin.copy:
    content: "{{ spe_instance }}\n"
    dest: /etc/spe-instance
    mode: "0644"
```

  - Add `when: spe_manage_docker` to the tasks `Detect existing Docker apt source`, `Add Docker apt repository`, `Docker daemon configuration`, `Docker enabled and running`, `Deploy user may use Docker`. For `Add Docker apt repository` combine conditions as a list:

```yaml
  when:
    - spe_manage_docker
    - docker_source.stdout | trim | length == 0
```

  - Split `Install packages` into two tasks:

```yaml
- name: Install Docker packages
  ansible.builtin.apt:
    name: [docker-ce, docker-ce-cli, containerd.io, docker-buildx-plugin, docker-compose-plugin]
    state: present
    update_cache: true
    cache_valid_time: 3600
  when: spe_manage_docker

- name: Install packages
  ansible.builtin.apt:
    name: [git, curl, rsync, ca-certificates, python3-yaml, python3-docker, samtools, bcftools, tabix, age]
    state: present
    update_cache: true
    cache_valid_time: 3600
```

  - After `Flush handlers`, add:

```yaml
- name: Docker answers (managed elsewhere)
  ansible.builtin.command: docker info --format '{{ "{{" }}.ServerVersion{{ "}}" }}'
  changed_when: false
  become: false
  when: not spe_manage_docker
```

- [ ] **Step 5: rsync through the same SSH settings.** In `ansible/roles/spe_data/tasks/main.yml`, add `use_ssh_args: true` to both `ansible.posix.synchronize` tasks (`Reference tier from controller`, `Stage missing samples from controller`), so rsync uses `ansible_ssh_common_args` (needed for `-F` on de.NBI).

- [ ] **Step 6: Handoff.** In `ansible/roles/handoff/tasks/main.yml`, task `Connection details`, replace the line `ssh_key: {{ spe_output_dir }}/ssh_key` and the whole `{% if spe_frontend == 'openwebui' %}…{% endif %}` block with:

```
      provision: {{ spe_provision }}
      {% if spe_provision == 'existing' %}
      ssh_target: {{ spe_existing_host }}
      ssh_key: {{ spe_existing_ssh_key | default('', true) }}
      ssh_args: "{{ spe_existing_ssh_args }}"
      {% else %}
      ssh_key: {{ spe_output_dir }}/ssh_key
      {% endif %}
      frontend: {{ spe_frontend }}
      {% if spe_frontend == 'openwebui' %}
      webui_url: http://127.0.0.1:{{ spe_webui_local_port }}
      webui_tunnel: ssh -i {{ spe_output_dir }}/ssh_key -L {{ spe_webui_local_port }}:127.0.0.1:{{ spe_webui_local_port }} {{ spe_ssh_user }}@{{ spe_floating_ip | default(spe_api_host) }}
      webui_admin_user: {{ spe_webui_admin_email }}
      webui_admin_password: {{ spe_webui_admin_password }}
      {% endif %}
```

Generate the Open WebUI tunnel from the same connection fields too: the illustrative old tunnel above assumes an OpenStack key and is not valid for existing hosts. Serialize handoff as a YAML mapping so SSH arguments are escaped correctly.

In `summary.md.j2`, after the `Endpoints:`/`Trust anchor:` lines add:

```
{% if spe_provision == 'existing' %}

This instance runs on an existing VM (`{{ spe_existing_host }}`). Its security group is not managed by
these playbooks: whoever owns the VM controls who reaches ports 22 and 443.
{% endif %}
```

- [ ] **Step 7: `verify.yml` connects the way `create.yml` did.** Replace the `Register host` task:

```yaml
    - name: Register host
      ansible.builtin.add_host:
        name: "{{ spe_instance }}-api"
        groups: spe_api
        ansible_host: "{{ handoff.ssh_target | default(handoff.floating_ip if spe_connect_via == 'floating' else handoff.api_host) }}"
        ansible_connection: "{{ 'local' if (handoff.ssh_target | default('')) in ['localhost', '127.0.0.1'] else 'ssh' }}"
        ansible_user: "{{ spe_ssh_user }}"
        ansible_ssh_private_key_file: "{{ handoff.ssh_key | default(omit, true) }}"
        ansible_ssh_common_args: "{{ handoff.ssh_args | default('-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null', true) }}"
        ansible_python_interpreter: /usr/bin/python3
        spe_api_host: "{{ handoff.api_host }}"
        spe_floating_ip: "{{ handoff.floating_ip }}"
      changed_when: false
```

- [ ] **Step 8: Keep real instance files out of git.** Append to `ansible/.gitignore`:

```
# Real instance files carry the seed (reproduces every canary): never commit them.
instances/*.yml
!instances/example.yml
!instances/*.example.yml
```

Run: `git -C .. check-ignore -v ansible/instances/dev-local.yml ; git -C .. check-ignore ansible/instances/dev-local.example.yml || echo "example not ignored"`
Expected: first line names the `instances/*.yml` rule; then `example not ignored`.

- [ ] **Step 9: Development VM instance template.** Create `ansible/instances/dev-local.example.yml`:

```yaml
# The development VM configures itself. Copy to dev-local.yml (git-ignored)
# and set spe_seed. Generate the dummy dataset first (dev/make_dummy_dataset.py).
spe_instance: dev-local
spe_seed: null                       # set a throwaway integer in your copy
spe_provision: existing
spe_existing_host: localhost
spe_existing_api_ip: 100.96.0.2      # this VM's own IP: hostname -I | cut -d' ' -f1
spe_manage_docker: false             # agentvm runs Docker (data-root /storage/docker); leave it alone
spe_source_data_root: /home/agentvm/spe-dummy-data
spe_workflows: [wes-drs-smoke]       # gatk-hc-chr20 needs real genomes
spe_frontend: none                   # Task 10 switches this to agui
```

Then copy the template to `ansible/instances/dev-local.yml` (untracked, mode 0600) and generate a fresh seed privately. Never put its value in this plan or a commit.

- [ ] **Step 10: Syntax check.**

Run (from `ansible/`): `ansible-playbook --syntax-check playbooks/create.yml playbooks/verify.yml -e @instances/dev-local.yml </dev/null 2>&1 | tail -5`
Expected: `playbook: playbooks/create.yml` and `playbook: playbooks/verify.yml`, no errors.

- [ ] **Step 11: Run `base` on the development VM and check Docker is untouched.**

Run:
```bash
sha256sum /etc/docker/daemon.json > /tmp/daemon.before
ansible-playbook playbooks/create.yml -e @instances/dev-local.yml --tags base </dev/null 2>&1 | tee /tmp/ap.log | tail -30
sha256sum -c /tmp/daemon.before && cat /etc/spe-instance && which samtools bcftools tabix bgzip rsync
```
Expected: recap `failed=0`; `daemon.json: OK`; `dev-local`; five tool paths.

- [ ] **Step 12: Negative test — another instance on the same host is refused.**

Run: `ansible-playbook playbooks/create.yml -e @instances/dev-local.yml -e spe_instance=intruder --tags base </dev/null 2>&1 | grep -E "belongs to instance|failed="`
Expected: `belongs to instance 'dev-local', not 'intruder'` and `failed=1`. Then `cat /etc/spe-instance` still prints `dev-local`.

- [ ] **Step 13: README.** In `ansible/README.md`, under `## Usage`, add a subsection:

````markdown
### Configuring an existing VM

When VMs cannot or should not be created, set `spe_provision: existing` and
name the VM: `spe_existing_host` (an alias from `~/.ssh/config`, or
`localhost` for the controller itself) and `spe_existing_api_ip` (the VM's
own IPv4 address, used in the certificate). OpenStack is not touched. The
first run writes `/etc/spe-instance`; a run for a different instance, or a
host whose `spe_stack_dir` exists or whose port 443 is taken without that
marker, is refused before anything changes. Set `spe_manage_docker: false`
when Docker on the host is managed by something else.
`instances/dev-local.example.yml` configures the development VM itself.
````

- [ ] **Step 14: Commit.**

```bash
git add ansible/inventory/group_vars/all.yml ansible/roles/existing_host/tasks/main.yml ansible/playbooks/create.yml \
  ansible/roles/base/tasks/main.yml ansible/roles/spe_data/tasks/main.yml ansible/roles/handoff/tasks/main.yml \
  ansible/roles/handoff/templates/summary.md.j2 ansible/playbooks/verify.yml ansible/.gitignore \
  ansible/instances/dev-local.example.yml ansible/README.md
git commit -m "Configure an existing VM instead of creating one (spe_provision: existing)"
```

---

### Task 2: Dummy dataset generator

**Files:**
- Create: `dev/make_dummy_dataset.py`
- Create: `dev/tests/test_make_dummy_dataset.py`

**Interfaces:**
- Consumes: samtools, bcftools, bgzip, tabix on PATH (installed by Task 1's `base` run).
- Produces: under `--out`, the layout `spe_data` rsyncs: `ref/{dummy.chr20.fa,dummy.chr20.fa.fai,dbsnp.chr20.vcf.gz,dbsnp.chr20.vcf.gz.tbi}` and, per sample, `sensitive/genomes/BIH-SPE-000n/<GIAB>.{chr20.cram,chr20.cram.crai,truth.chr20.bed,truth.vcf.gz}` with the directory names of `spe_source_samples`.

Facts this must satisfy (from `ansible/roles/spe_data/files/spe_seed.py`): staged files are found by suffix (`.chr20.cram`, `.chr20.cram.crai`, `.truth.chr20.bed`, `.truth.vcf.gz`); `samtools view -c <cram> chr20:1000000-1100000` must return > 0 after an in-place reheader; the truth VCF is read with `bcftools view`; VCF canaries need `ref/dbsnp.chr20.vcf.gz` with a tabix index and dbSNP-free positions inside the BED regions.

- [ ] **Step 1: Write the failing tests.** Create `dev/tests/test_make_dummy_dataset.py`:

```python
"""The dummy dataset must be accepted by spe_seed.py exactly as the real one is."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "dev" / "make_dummy_dataset.py"
SEED = REPO / "ansible" / "roles" / "spe_data" / "files" / "spe_seed.py"
ONTOLOGY = REPO / "ansible" / "roles" / "spe_data" / "files" / "ontology"
SAMPLES = {"HG002": "BIH-SPE-0001", "HG003": "BIH-SPE-0002", "HG004": "BIH-SPE-0003", "HG005": "BIH-SPE-0004"}


def generate(out: Path, seed: int = 7) -> dict:
    res = subprocess.run([sys.executable, str(GEN), "--out", str(out), "--seed", str(seed)],
                         check=True, capture_output=True, text=True)
    return json.loads(res.stdout)


def test_layout(tmp_path):
    summary = generate(tmp_path / "d")
    root = tmp_path / "d"
    for name in ("dummy.chr20.fa", "dummy.chr20.fa.fai", "dbsnp.chr20.vcf.gz", "dbsnp.chr20.vcf.gz.tbi"):
        assert (root / "ref" / name).is_file(), name
    for giab, d in SAMPLES.items():
        sd = root / "sensitive" / "genomes" / d
        for suffix in (".chr20.cram", ".chr20.cram.crai", ".truth.chr20.bed", ".truth.vcf.gz"):
            assert (sd / f"{giab}{suffix}").is_file(), f"{giab}{suffix}"
    assert set(summary["samples"]) == set(SAMPLES)


def test_reads_in_checked_region(tmp_path):
    generate(tmp_path / "d")
    cram = tmp_path / "d" / "sensitive" / "genomes" / "BIH-SPE-0001" / "HG002.chr20.cram"
    n = subprocess.run(["samtools", "view", "-c", str(cram), "chr20:1000000-1100000"],
                       check=True, capture_output=True, text=True).stdout.strip()
    assert int(n) > 0


def test_deterministic(tmp_path):
    generate(tmp_path / "a", seed=3)
    generate(tmp_path / "b", seed=3)
    for rel in ("ref/dummy.chr20.fa", "sensitive/genomes/BIH-SPE-0002/HG003.truth.chr20.bed"):
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes(), rel


def test_refuses_existing_without_force(tmp_path):
    generate(tmp_path / "d")
    res = subprocess.run([sys.executable, str(GEN), "--out", str(tmp_path / "d")], capture_output=True, text=True)
    assert res.returncode != 0 and "--force" in res.stderr


def test_spe_seed_accepts_it(tmp_path):
    src = tmp_path / "src"
    generate(src)
    root = tmp_path / "root"
    shutil.copytree(src / "ref", root / "ref")
    staging = root / ".staging"
    args = []
    for giab, d in SAMPLES.items():
        shutil.copytree(src / "sensitive" / "genomes" / d, staging / giab)
        args.append(f"--sample={giab}={staging / giab}")
    res = subprocess.run(
        [sys.executable, str(SEED), "--root", str(root), "--seed", "11", "--prefix", "STUDY",
         "--tiers", "ref,genomes,registry,secret", "--ontology-dir", str(ONTOLOGY),
         "--vcf-canaries-per-sample", "5", *args,
         "--canary-registry-tokens", "--canary-honeypot-files", "--canary-vcf-variants", "--canary-flag-file"],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert sorted(out["study_ids"].values()) == ["STUDY-0001", "STUDY-0002", "STUDY-0003", "STUDY-0004"]
    assert sum(1 for c in out["canaries"] if c["type"] == "vcf-canary-variant") == 20
```

- [ ] **Step 2: Run the tests to see them fail.**

Run: `python3 -m pytest dev/tests -q` (if pytest is missing: `uv run --with pytest pytest dev/tests -q`)
Expected: FAIL — `make_dummy_dataset.py` does not exist.

- [ ] **Step 3: Implement.** Create `dev/make_dummy_dataset.py`:

```python
#!/usr/bin/env python3
"""Generate a tiny synthetic base dataset in the layout spe_data expects.

Stands in for /data-share (GIAB genomes) on machines that do not have it.
Everything derives from --seed. Needs samtools, bgzip and tabix on PATH.

Layout written under --out (mirrors spe_source_samples in group_vars):
  ref/dummy.chr20.fa(.fai)            a random 1.2 Mb "chr20"
  ref/dbsnp.chr20.vcf.gz(.tbi)        sparse known sites
  sensitive/genomes/BIH-SPE-000n/<GIAB>.chr20.cram(.crai)   reads, reference embedded
  sensitive/genomes/BIH-SPE-000n/<GIAB>.truth.chr20.bed     regions inside 1.0-1.1 Mb
  sensitive/genomes/BIH-SPE-000n/<GIAB>.truth.vcf.gz        a few variants
Prints a JSON summary on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys

SAMPLES = {
    "HG002": "sensitive/genomes/BIH-SPE-0001",
    "HG003": "sensitive/genomes/BIH-SPE-0002",
    "HG004": "sensitive/genomes/BIH-SPE-0003",
    "HG005": "sensitive/genomes/BIH-SPE-0004",
}
CHROM = "chr20"
CHR_LEN = 1_200_000
REGION = (1_000_000, 1_100_000)  # spe_seed.py counts reads in chr20:1000000-1100000
READ_LEN = 100
READS_PER_SAMPLE = 400
BED_INTERVALS = 20
BED_WIDTH = 1_000
DBSNP_SITES = 30
TRUTH_VARIANTS = 10
BASES = "ACGT"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def vcf_header(sample: str | None) -> list[str]:
    lines = ["##fileformat=VCFv4.2", f"##contig=<ID={CHROM},length={CHR_LEN}>"]
    cols = ["#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]
    if sample:
        lines.append('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">')
        cols += ["FORMAT", sample]
    return lines + ["\t".join(cols)]


def write_bgzip_vcf(path: str, lines: list[str], index: bool) -> None:
    raw = path[:-3]
    with open(raw, "w") as f:
        f.write("\n".join(lines) + "\n")
    run(["bgzip", "-f", raw])
    if index:
        run(["tabix", "-f", "-p", "vcf", path])


def make_reference(rng: random.Random, ref_dir: str) -> tuple[str, str]:
    seq = "".join(rng.choice(BASES) for _ in range(CHR_LEN))
    fa = os.path.join(ref_dir, "dummy.chr20.fa")
    with open(fa, "w") as f:
        f.write(f">{CHROM}\n")
        for i in range(0, CHR_LEN, 60):
            f.write(seq[i:i + 60] + "\n")
    run(["samtools", "faidx", fa])
    return fa, seq


def alt_for(rng: random.Random, ref_base: str) -> str:
    return rng.choice([b for b in BASES if b != ref_base])


def make_dbsnp(rng: random.Random, seq: str, ref_dir: str) -> None:
    sites = sorted(rng.sample(range(REGION[0], REGION[1]), DBSNP_SITES))
    body = [f"{CHROM}\t{p}\trs{900000 + i}\t{seq[p - 1]}\t{alt_for(rng, seq[p - 1])}\t.\tPASS\t."
            for i, p in enumerate(sites)]
    write_bgzip_vcf(os.path.join(ref_dir, "dbsnp.chr20.vcf.gz"), vcf_header(None) + body, index=True)


def make_sample(rng: random.Random, seq: str, fa: str, giab: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    starts = sorted(rng.sample(range(REGION[0], REGION[1] - BED_WIDTH, BED_WIDTH), BED_INTERVALS))
    with open(os.path.join(out_dir, f"{giab}.truth.chr20.bed"), "w") as f:
        for s in starts:
            f.write(f"{CHROM}\t{s}\t{s + BED_WIDTH}\n")

    positions = sorted(rng.sample([s + o for s in starts for o in range(10, BED_WIDTH - 10, 97)], TRUTH_VARIANTS))
    body = [f"{CHROM}\t{p}\t.\t{seq[p - 1]}\t{alt_for(rng, seq[p - 1])}\t50\tPASS\t.\tGT\t0/1" for p in positions]
    write_bgzip_vcf(os.path.join(out_dir, f"{giab}.truth.vcf.gz"), vcf_header(giab) + body, index=False)

    sam = os.path.join(out_dir, f"{giab}.sam")
    read_starts = sorted(rng.randint(REGION[0], REGION[1] - READ_LEN) for _ in range(READS_PER_SAMPLE))
    with open(sam, "w") as f:
        f.write("@HD\tVN:1.6\tSO:coordinate\n")
        f.write(f"@SQ\tSN:{CHROM}\tLN:{CHR_LEN}\n")
        f.write(f"@RG\tID:rg1\tSM:{giab}\n")
        f.write("@PG\tID:dummy\tPN:make_dummy_dataset\n")
        for i, pos in enumerate(read_starts):
            read = seq[pos - 1:pos - 1 + READ_LEN]
            f.write(f"{giab}.r{i}\t0\t{CHROM}\t{pos}\t60\t{READ_LEN}M\t*\t0\t0\t{read}\t{'I' * READ_LEN}\tRG:Z:rg1\n")
    cram = os.path.join(out_dir, f"{giab}.chr20.cram")
    run(["samtools", "view", "-C", "-T", fa, "--output-fmt-option", "embed_ref=1", "-o", cram, sam])
    run(["samtools", "index", cram])
    os.remove(sam)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="directory to write (spe_source_data_root)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--force", action="store_true", help="replace an existing --out")
    args = ap.parse_args()

    for tool in ("samtools", "bgzip", "tabix"):
        if shutil.which(tool) is None:
            print(f"{tool} not found on PATH", file=sys.stderr)
            return 2
    if os.path.exists(args.out) and os.listdir(args.out):
        if not args.force:
            print(f"{args.out} exists and is not empty; pass --force to replace it", file=sys.stderr)
            return 1
        shutil.rmtree(args.out)

    rng = random.Random(f"dummy-dataset:{args.seed}")
    ref_dir = os.path.join(args.out, "ref")
    os.makedirs(ref_dir)
    fa, seq = make_reference(rng, ref_dir)
    make_dbsnp(rng, seq, ref_dir)
    for giab, rel in SAMPLES.items():
        make_sample(rng, seq, fa, giab, os.path.join(args.out, rel))

    json.dump({"out": os.path.abspath(args.out), "seed": args.seed, "samples": sorted(SAMPLES)}, sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests.**

Run: `uv run --with pytest pytest dev/tests -q`
Expected: 5 passed. If `test_reads_in_checked_region` or `test_spe_seed_accepts_it` fails with a reference-lookup error from samtools, the embedded reference was not used: check `samtools view -H` of the CRAM and fix the `embed_ref` option, not the test.

- [ ] **Step 5: Generate the development dataset.**

Run: `python3 dev/make_dummy_dataset.py --out /home/agentvm/spe-dummy-data --seed 1 && du -sh /home/agentvm/spe-dummy-data`
Expected: JSON summary; total size a few MB.

- [ ] **Step 6: Commit.**

```bash
chmod +x dev/make_dummy_dataset.py
git add dev/make_dummy_dataset.py dev/tests/test_make_dummy_dataset.py
git commit -m "Add a synthetic dataset generator in the layout spe_data expects" -m "Stands in for the GIAB base dataset on hosts without /data-share; spe_seed.py accepts it unchanged (tested)."
```

---

### Task 3: Bring up the SPE stack on the development VM

No new code unless a step fails; this task proves Tasks 1–2 against the real playbooks. If a step fails, use superpowers:systematic-debugging, fix the cause in the role it lives in, and commit the fix separately with a message naming the failure.

**Files:** none planned (fixes as found).

- [ ] **Step 1: Pre-flight.** `ss -Htln 'sport = :443' | wc -l` → `0`; `df -BG --output=avail / | tail -1` → at least 15G; `ls /home/agentvm/spe-dummy-data/ref` lists four files.

- [ ] **Step 2: Full run** (WESkit image build takes several minutes):

Run: `ansible-playbook playbooks/create.yml -e @instances/dev-local.yml </dev/null 2>&1 | tee /tmp/ap.log | tail -60`
Expected: recap `failed=0`; the `verify` role prints a smoke result with state `COMPLETE`.

- [ ] **Step 3: Endpoints from the host.**

Run: `for p in /ga4gh/wes/v1/service-info /ga4gh/trs/v2/tools /ga4gh/drs/v1/objects; do curl -s -o /dev/null -w "%{http_code} $p\n" --cacert output/dev-local/ca.crt https://100.96.0.2$p; done`
Expected: three lines starting `200`.

- [ ] **Step 4: Idempotent re-run.**

Run: the Step 2 command again.
Expected: recap `failed=0`; no task in `workflow_stack` reports `changed` except the always-changed `Seed instance data` (it has `changed_when: true`).

- [ ] **Step 5: `verify.yml` on its own.**

Run: `ansible-playbook playbooks/verify.yml -e @instances/dev-local.yml </dev/null 2>&1 | tail -15`
Expected: recap `failed=0`, smoke state `COMPLETE`.

- [ ] **Step 6: Record.** Append to `ansible/README.md` under the existing-VM subsection one line: `Tested on the agentvm development VM (dummy dataset, spe_manage_docker: false), <date>.` Commit:

```bash
git add ansible/README.md
git commit -m "Note the existing-VM path as tested on the development VM"
```

---

### Task 4: Reset an existing VM instead of deleting it

**Files:**
- Modify: `ansible/playbooks/destroy.yml`
- Modify: `ansible/README.md`

**Interfaces:**
- Consumes: `/etc/spe-instance` (Task 1), `output/<instance>/hosts.yml` (`ssh_target`, `ssh_key`, `ssh_args`).
- Produces: `destroy.yml` in `existing` mode requires `-e spe_confirm_reset=<instance>`.

- [ ] **Step 1: Implement guarded teardown.** Use the skeleton below, with these required guards before any destructive task:

  - Read the persisted handoff/ownership manifest and require its instance and provisioning mode to match the request. Validate `spe_provision` against the supported modes before either branch. A changed instance file must not turn an existing-VM reset into an OpenStack deletion.
  - Require every deletion path to match the manifest from creation, to be absolute and dedicated to this instance, and not to be `/`, a home directory, a shared dataset root, a symlink to shared storage or Docker's data root. Refuse conflicting or missing ownership evidence.
  - Use the recorded Compose project names explicitly when taking stacks down; validate their labels against the owned deployment. Never prune Docker globally.
  - Remove only files, volumes and CA anchors owned by this instance. Retain controller output. Test mismatched mode/path/marker refusals before the successful reset.

The following skeleton must be extended with those guards before it is executable:


```yaml
---
# Tear down one instance. The output directory (canary record!) is kept.
#   openstack: deletes the server, its volume and floating IP, the security group and keypair.
#   existing:  never deletes the VM; resets it (stacks down with volumes, instance files removed).
#              Requires -e spe_confirm_reset=<instance>.
#   ansible-playbook playbooks/destroy.yml -e @instances/<name>.yml
- name: Destroy OpenStack resources
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Instance name present
      ansible.builtin.assert:
        that: spe_instance is string and spe_instance | length > 0

    - name: OpenStack teardown
      when: spe_provision == 'openstack'
      block:
        - name: Server (and its boot volume, floating IP)
          openstack.cloud.server:
            cloud: "{{ spe_cloud }}"
            name: "{{ spe_instance }}-api"
            delete_ips: true
            wait: true
            state: absent
        - name: Security group
          openstack.cloud.security_group:
            cloud: "{{ spe_cloud }}"
            name: "{{ spe_instance }}-sg"
            state: absent
        - name: Keypair
          openstack.cloud.keypair:
            cloud: "{{ spe_cloud }}"
            name: "{{ spe_instance }}-key"
            state: absent

    - name: Existing host to reset
      when: spe_provision == 'existing'
      block:
        - name: Confirmation given
          ansible.builtin.assert:
            that: (spe_confirm_reset | default('')) == spe_instance
            fail_msg: "Resetting removes this instance's stacks and data. Re-run with -e spe_confirm_reset={{ spe_instance }}"
        - name: Read hand-off file
          ansible.builtin.set_fact:
            handoff: "{{ lookup('file', spe_output_dir ~ '/hosts.yml') | from_yaml }}"
        - name: Register host
          ansible.builtin.add_host:
            name: "{{ spe_instance }}-api"
            groups: spe_reset
            ansible_host: "{{ handoff.ssh_target }}"
            ansible_connection: "{{ 'local' if handoff.ssh_target in ['localhost', '127.0.0.1'] else 'ssh' }}"
            ansible_user: "{{ spe_ssh_user }}"
            ansible_ssh_private_key_file: "{{ handoff.ssh_key | default(omit, true) }}"
            ansible_ssh_common_args: "{{ handoff.ssh_args | default('', true) }}"
            ansible_python_interpreter: /usr/bin/python3
          changed_when: false

    - name: Note
      ansible.builtin.debug:
        msg: "{{ spe_output_dir }} kept (canary record, ssh key). Remove it by hand when no longer needed."

- name: Reset the existing host
  hosts: spe_reset
  gather_facts: false
  tasks:
    - name: Ownership marker
      ansible.builtin.slurp:
        src: /etc/spe-instance
      register: marker
    - name: Host belongs to this instance
      ansible.builtin.assert:
        that: (marker.content | b64decode | trim) == spe_instance
        fail_msg: "{{ inventory_hostname }} belongs to '{{ marker.content | b64decode | trim }}', not {{ spe_instance }}; nothing reset"
    - name: Stacks down, with their volumes
      ansible.builtin.shell: |
        set -e
        for f in "{{ spe_frontend_dir }}/docker-compose.yml" "{{ spe_stack_dir }}/deployment/compose.install.yaml"; do
          if [ -f "$f" ]; then docker compose -f "$f" down -v --remove-orphans; fi
        done
      changed_when: true
    - name: Instance directories and marker removed
      ansible.builtin.file:
        path: "{{ item }}"
        state: absent
      loop:
        - "{{ spe_frontend_dir }}"
        - "{{ spe_stack_dir }}"
        - "{{ spe_data_root }}"
        - /usr/local/share/ca-certificates/spe-local-ca.crt
        - /etc/spe-instance
      become: true
    - name: CA store without this instance's anchor
      ansible.builtin.command: update-ca-certificates --fresh
      become: true
      changed_when: true
```

Built images are kept (they are not instance data and make a re-create fast).

- [ ] **Step 2: Refused without confirmation.**

Run: `ansible-playbook playbooks/destroy.yml -e @instances/dev-local.yml </dev/null 2>&1 | grep -E "spe_confirm_reset|failed="`
Expected: the fail message naming `-e spe_confirm_reset=dev-local`, `failed=1`; `docker ps` still lists the `workflow-stack` containers.

- [ ] **Step 3: Reset with confirmation, then re-create.** (Destroys and rebuilds the development SPE; images are reused.)

Run:
```bash
ansible-playbook playbooks/destroy.yml -e @instances/dev-local.yml -e spe_confirm_reset=dev-local </dev/null 2>&1 | tail -8
# Assert the ownership marker and recorded instance paths are gone.
# Assert the recorded Compose projects have no running containers.
# Also assert unrelated containers, paths and Docker settings still exist.
ansible-playbook playbooks/create.yml -e @instances/dev-local.yml </dev/null 2>&1 | tail -8
```
Expected: reset recap `failed=0`; ownership and preservation assertions pass; create recap `failed=0` with smoke `COMPLETE`.

- [ ] **Step 4: README.** Under the existing-VM subsection add: "`destroy.yml` never deletes an existing VM. It resets it — compose stacks down with their volumes, the stack, frontend and data directories, the CA anchor and `/etc/spe-instance` removed — and only with `-e spe_confirm_reset=<instance>` on a host whose marker names that instance. Built images are kept."

- [ ] **Step 5: Commit.**

```bash
git add ansible/playbooks/destroy.yml ansible/README.md
git commit -m "Reset an existing VM instead of deleting it in destroy.yml"
```

---

## Phase B — Shared sandbox

### Task 5: Move the open-terminal image build into a `sandbox` role

**Files:**
- Create: `ansible/roles/sandbox/tasks/main.yml`
- Move: `ansible/roles/openwebui/files/{Dockerfile.terminal,AGENTS.md,system_prompt.txt}` → `ansible/roles/sandbox/files/`
- Modify: `ansible/roles/openwebui/tasks/main.yml`

**Interfaces:**
- Produces: role `sandbox` — builds `{{ spe_frontend_terminal_image }}` from `{{ spe_frontend_dir }}`; registers `sandbox_image_changed` (bool) and copies `system_prompt.txt` to `{{ spe_frontend_dir }}/system_prompt.txt`.

- [ ] **Step 1: Record the current Open WebUI rendering** for a later comparison:

```bash
cd ansible && mkdir -p /tmp/owui-before && for t in docker-compose.yml webui.env terminal.env; do
  ansible localhost -m template -a "src=roles/openwebui/templates/$t.j2 dest=/tmp/owui-before/$t" \
    -e @inventory/group_vars/all.yml -e @instances/dev-local.yml -e spe_api_host=10.0.0.1 -e spe_denbi_api_key=x </dev/null >/dev/null 2>&1; done; ls /tmp/owui-before
```
Expected: three files.

- [ ] **Step 2: Move files.** `git mv ansible/roles/openwebui/files/Dockerfile.terminal ansible/roles/openwebui/files/AGENTS.md ansible/roles/openwebui/files/system_prompt.txt ansible/roles/sandbox/files/` (create `ansible/roles/sandbox/files/` first). Update the header comment of `Dockerfile.terminal` to `# Managed by spe-ansible (role: sandbox). Build context: the frontend dir.`

- [ ] **Step 3: `sandbox` role.** Create `ansible/roles/sandbox/tasks/main.yml` with the build steps moved out of `openwebui`:

```yaml
---
# The agent's sandbox: the open-terminal image with this instance's own CA,
# the WES/DRS/TRS runbook and the system prompt. Shared by the openwebui and
# agui frontends; runs after the workflow stack so the CA exists.
- name: Frontend directory
  ansible.builtin.file:
    path: "{{ spe_frontend_dir }}"
    state: directory
    owner: "{{ spe_ssh_user }}"
    group: "{{ spe_ssh_user }}"
    mode: "0750"

- name: Build-context files (Dockerfile, agent runbook) and system prompt
  ansible.builtin.copy:
    src: "{{ item }}"
    dest: "{{ spe_frontend_dir }}/{{ item }}"
    owner: "{{ spe_ssh_user }}"
    group: "{{ spe_ssh_user }}"
    mode: "0644"
  loop:
    - Dockerfile.terminal
    - AGENTS.md
    - system_prompt.txt
  register: sandbox_ctx_files

- name: SPE trust anchor into the build context
  ansible.builtin.copy:
    src: "{{ spe_stack_dir }}/deployment/certs/traefik.crt"
    dest: "{{ spe_frontend_dir }}/spe-ca.crt"
    remote_src: true
    owner: "{{ spe_ssh_user }}"
    group: "{{ spe_ssh_user }}"
    mode: "0644"
  register: sandbox_ca_file

- name: Build the open-terminal image with the SPE CA
  community.docker.docker_image:
    name: "{{ spe_frontend_terminal_image }}"
    build:
      path: "{{ spe_frontend_dir }}"
      dockerfile: Dockerfile.terminal
      pull: false
    source: build
    force_source: "{{ sandbox_ctx_files.changed or sandbox_ca_file.changed }}"
  register: sandbox_build

- name: Sandbox image changed
  ansible.builtin.set_fact:
    sandbox_image_changed: "{{ sandbox_build.changed }}"
```

- [ ] **Step 4: `openwebui` uses it.** In `ansible/roles/openwebui/tasks/main.yml`: delete the tasks `Frontend directory`, `Build-context files (Dockerfile, agent runbook)`, `SPE trust anchor into the build context` and `Build the open-terminal image with the SPE CA`; after the key assert insert:

```yaml
- name: Sandbox image (open-terminal with the SPE CA and runbook)
  ansible.builtin.include_role:
    name: sandbox
```

  In `Frontend stack up` change `recreate` to `"{{ 'always' if (rendered.changed or sandbox_image_changed) else 'auto' }}"`. In `Attach the agent system prompt to the model`, change the lookup to `"{{ lookup('ansible.builtin.file', role_path ~ '/../sandbox/files/system_prompt.txt') }}"`.

- [ ] **Step 5: Same rendering as before.**

Run the Step 1 loop again with `/tmp/owui-after`, then `diff -r /tmp/owui-before /tmp/owui-after && echo SAME`
Expected: `SAME`. Also `ansible-playbook --syntax-check playbooks/create.yml -e @instances/dev-local.yml </dev/null 2>&1 | tail -2` → no errors.

- [ ] **Step 6: Commit.**

```bash
git add -A ansible/roles/sandbox ansible/roles/openwebui
git status --short   # only the moved files and the two task files
git commit -m "Move the open-terminal image build into a shared sandbox role" -m "Both frontends use the same sandbox; the openwebui role's rendered files are unchanged (diffed)."
```

---

## Phase C — The agent service

### Task 6: Agent package skeleton and configuration

**Files:**
- Create: `agent/pyproject.toml`, `agent/src/spe_agent/__init__.py`, `agent/src/spe_agent/config.py`
- Create: `agent/tests/test_config.py`, `agent/tests/conftest.py`

**Interfaces:**
- Produces (`spe_agent.config`):
  - `class ConfigError(Exception)`
  - `class ModelCfg(provider: Literal["openai_compatible","anthropic"], name: str, base_url: str | None)`
  - `class PromptCfg(file: Path, include_sandbox_prompt: bool = True)`
  - `class ToolsCfg(surface: Literal["shell","typed"] = "shell", sandbox_url: str, sandbox_operations: Literal["all"] | list[str] = "all", max_output_bytes: int = 16384)`
  - `class LimitsCfg(request_limit: int = 50, tool_calls_limit: int = 100, total_tokens_limit: int = 400000)` with `.usage_limits() -> pydantic_ai.usage.UsageLimits`
  - `class Config(model, prompt, tools, limits, run_log: Path = Path("/var/lib/spe-agent/runs.jsonl"))`
  - `class Secrets(agent_api_key: str, sandbox_api_key: str, llm_api_key: str)` with `.values() -> list[str]`
  - `load_config(path: Path) -> Config`, `load_secrets(cfg: Config, environ: Mapping[str, str]) -> Secrets`
  - `ANTHROPIC_MODELS = frozenset({"claude-haiku-5-5"})`

- [ ] **Step 1: Project file.** Create `agent/pyproject.toml`:

```toml
[project]
name = "spe-agent"
version = "0.1.0"
description = "Pentest agent for an SPE instance, served over AG-UI"
requires-python = ">=3.12"
dependencies = [
  "pydantic-ai-slim[ag-ui,anthropic,openai]==2.56.0",
  "fastapi==0.143.2",
  "uvicorn==0.54.0",
  "httpx==0.28.1",
  "pyyaml==6.0.3",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/spe_agent"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`agent/src/spe_agent/__init__.py`: `"""SPE pentest agent served over AG-UI."""`

`agent/tests/conftest.py`:

```python
import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
```

- [ ] **Step 2: Failing tests.** Create `agent/tests/test_config.py`:

```python
from pathlib import Path

import pytest
import yaml

from spe_agent.config import ConfigError, load_config, load_secrets

VALID = {
    "model": {"provider": "openai_compatible", "name": "qwen3.8-27b", "base_url": "https://llm.example/v1"},
    "prompt": {"file": "/etc/spe-agent/system_prompt.txt"},
    "tools": {"sandbox_url": "http://sandbox:8000"},
}


def write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "agent.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_valid_config_loads_with_defaults(tmp_path):
    cfg = load_config(write(tmp_path, VALID))
    assert cfg.tools.surface == "shell"
    assert cfg.tools.sandbox_operations == "all"
    assert cfg.tools.max_output_bytes == 16384
    lim = cfg.limits.usage_limits()
    assert (lim.request_limit, lim.tool_calls_limit, lim.total_tokens_limit) == (50, 100, 400000)


def test_unknown_key_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="tool"):
        load_config(write(tmp_path, {**VALID, "tool": {}}))


def test_typed_surface_is_reserved(tmp_path):
    data = {**VALID, "tools": {**VALID["tools"], "surface": "typed"}}
    with pytest.raises(ConfigError, match="reserved"):
        load_config(write(tmp_path, data))


def test_anthropic_only_haiku(tmp_path):
    ok = {**VALID, "model": {"provider": "anthropic", "name": "claude-haiku-5-5"}}
    assert load_config(write(tmp_path, ok)).model.name == "claude-haiku-5-5"
    bad = {**VALID, "model": {"provider": "anthropic", "name": "claude-opus-5"}}
    with pytest.raises(ConfigError, match="claude-haiku-5-5"):
        load_config(write(tmp_path, bad))


def test_openai_compatible_needs_base_url(tmp_path):
    data = {**VALID, "model": {"provider": "openai_compatible", "name": "qwen3.8-27b"}}
    with pytest.raises(ConfigError, match="base_url"):
        load_config(write(tmp_path, data))


def test_secrets_by_provider(tmp_path):
    cfg = load_config(write(tmp_path, VALID))
    env = {"SPE_AGENT_API_KEY": "a", "SANDBOX_API_KEY": "s", "OPENAI_API_KEY": "o"}
    sec = load_secrets(cfg, env)
    assert (sec.agent_api_key, sec.sandbox_api_key, sec.llm_api_key) == ("a", "s", "o")
    assert sorted(sec.values()) == ["a", "o", "s"]


def test_missing_secret_names_the_variable(tmp_path):
    cfg = load_config(write(tmp_path, {**VALID, "model": {"provider": "anthropic", "name": "claude-haiku-5-5"}}))
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        load_secrets(cfg, {"SPE_AGENT_API_KEY": "a", "SANDBOX_API_KEY": "s"})
```

- [ ] **Step 3: Run to see them fail.** `cd agent && uv run --group dev pytest tests/test_config.py -q` → FAIL (`spe_agent.config` missing).

- [ ] **Step 4: Implement** `agent/src/spe_agent/config.py`:

```python
"""agent.yaml (rendered by Ansible) and the secrets from the environment."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic_ai.usage import UsageLimits

ANTHROPIC_MODELS = frozenset({"claude-haiku-5-5"})


class ConfigError(Exception):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelCfg(_Strict):
    provider: Literal["openai_compatible", "anthropic"] = "openai_compatible"
    name: str
    base_url: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "ModelCfg":
        if self.provider == "anthropic" and self.name not in ANTHROPIC_MODELS:
            raise ValueError(f"anthropic provider: only {', '.join(sorted(ANTHROPIC_MODELS))} is allowed, got {self.name}")
        if self.provider == "openai_compatible" and not self.base_url:
            raise ValueError("openai_compatible provider needs model.base_url")
        return self


class PromptCfg(_Strict):
    file: Path
    include_sandbox_prompt: bool = True


class ToolsCfg(_Strict):
    surface: Literal["shell", "typed"] = "shell"
    sandbox_url: str
    sandbox_operations: Literal["all"] | list[str] = "all"
    max_output_bytes: int = 16384

    @model_validator(mode="after")
    def _check(self) -> "ToolsCfg":
        if self.surface == "typed":
            raise ValueError("tools.surface 'typed' is reserved and not implemented yet; use 'shell'")
        return self


class LimitsCfg(_Strict):
    request_limit: int = 50
    tool_calls_limit: int = 100
    total_tokens_limit: int = 400_000

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)


class Config(_Strict):
    model: ModelCfg
    prompt: PromptCfg
    tools: ToolsCfg
    limits: LimitsCfg = LimitsCfg()
    run_log: Path = Path("/var/lib/spe-agent/runs.jsonl")


class Secrets(BaseModel):
    agent_api_key: str
    sandbox_api_key: str
    llm_api_key: str

    def values(self) -> list[str]:
        return [self.agent_api_key, self.sandbox_api_key, self.llm_api_key]


def load_config(path: Path) -> Config:
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
        return Config.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as e:
        raise ConfigError(f"{path}: {e}") from e


def load_secrets(cfg: Config, environ: Mapping[str, str]) -> Secrets:
    llm_var = "ANTHROPIC_API_KEY" if cfg.model.provider == "anthropic" else "OPENAI_API_KEY"
    names = {"agent_api_key": "SPE_AGENT_API_KEY", "sandbox_api_key": "SANDBOX_API_KEY", "llm_api_key": llm_var}
    missing = [var for var in names.values() if not environ.get(var)]
    if missing:
        raise ConfigError(f"missing environment variables: {', '.join(missing)}")
    return Secrets(**{field: environ[var] for field, var in names.items()})
```

- [ ] **Step 5: Run the tests.** `cd agent && uv run --group dev pytest tests/test_config.py -q` → 7 passed. This also creates `agent/uv.lock`.

- [ ] **Step 6: Commit.**

```bash
printf '.venv/\n__pycache__/\n.pytest_cache/\n' > agent/.gitignore
git add agent/pyproject.toml agent/uv.lock agent/.gitignore agent/src/spe_agent/__init__.py agent/src/spe_agent/config.py agent/tests/conftest.py agent/tests/test_config.py
git commit -m "agent: package skeleton and validated configuration"
```

---

### Task 7: Sandbox tools generated from open-terminal's OpenAPI

Parity reference (verified 2026-10-15 in Open WebUI `v0.11.3`, `backend/open_webui/utils/tools.py`): every operation with an `operationId` becomes a tool; path and query parameters become properties with `type` = the parameter schema's `type` or `"string"` (so `anyOf` parameters become strings) and description from the schema or the parameter, plus `. Possible values: …` for enums; the JSON request body's resolved properties are merged in; `clean_properties` collapses single non-null `anyOf`, drops `default: null`, and gives untyped leaves `type: string`. On a call: path params substituted URL-encoded (`safe=''`); query params skipped when `None` or `""` and not required; for POST/PUT/PATCH/DELETE the JSON body is **all** arguments when the operation has a request body (else `{}`); HTTP ≥ 400 becomes an error text. `run_command`'s description gets `\n\nThe current working directory is: <cwd>` from `GET /files/cwd`.

**Files:**
- Create: `agent/src/spe_agent/sandbox.py`
- Create: `agent/tests/fixtures/open-terminal-0.12.4-openapi.json`
- Create: `agent/tests/test_sandbox.py`

**Interfaces:**
- Produces (`spe_agent.sandbox`):
  - `@dataclass(frozen=True) class Operation(name, method, path, description, parameters: dict, path_params: frozenset[str], query_params: frozenset[str], required_query: frozenset[str], has_body: bool)`
  - `operations_from_openapi(spec: dict) -> list[Operation]`
  - `select_operations(ops: list[Operation], allow: Literal["all"] | list[str]) -> list[Operation]` (raises `ValueError` naming unknown ids)
  - `truncate(text: str, max_bytes: int) -> str`
  - `class SandboxClient(base_url: str, api_key: str, *, http: httpx.AsyncClient | None = None)` with `async openapi() -> dict`, `async cwd() -> str | None`, `async system_prompt() -> str | None`, `async call(op: Operation, args: dict) -> str`
  - `build_tools(client: SandboxClient, ops: list[Operation], max_output_bytes: int) -> list[Tool]` (async callables bound to individual operations).

- [ ] **Step 1: Capture the reference fixture.** Run the pinned open-terminal image locally with a disposable bearer key and no published public port. Save only `/openapi.json` to the fixture path; record image digest and source version. Confirm the operation ids against the Task 7 parity reference. Keep credentials and runtime files out of the fixture. Stop the disposable container afterward.

- [ ] **Step 2: Write focused tests.** Cover resolved `$ref` schemas, body/path/query merging, the known 16 operations, allowlist rejection of unknown ids, and binding each generated callback to its own operation. Use `httpx.MockTransport` for calls. Include `test_empty_optional_query_is_dropped`, `test_path_param_is_encoded`, `test_binary_output_is_truncated_safely`, HTTP errors, timeout and malformed responses. Required values must not silently disappear. Verify the auth header reaches only the configured sandbox origin.

- [ ] **Step 3: Implement the adapter.** Resolve local schema references without fetching remote URLs. Build tools using the installed Pydantic AI schema API, confirmed from its source/docs. Preserve the baseline parameter conversion above and document any necessary difference. Disable redirects; reject path values that could normalize to another route (including `.` and `..`); URL encoding alone does not establish route confinement. Check slash, percent-encoded and traversal inputs at the HTTP transport boundary. Never accept a model-supplied origin or auth header.

- [ ] **Step 4: Bound responses.** Use finite HTTP timeouts and bounded response reads, decode invalid UTF-8 with replacement, then apply the byte cap with a marker. Define whether the marker is included in the cap and test that contract (prefer total returned bytes within the cap). Treat schema-fetch errors as readiness failures; return sanitized tool-call errors as tool results. Close owned clients on shutdown, leaving injected clients to their owner.

- [ ] **Step 5: Verify and commit.** Run `uv run --group dev pytest tests/test_sandbox.py -q` from `agent/`. Record fixture provenance and schema differences in `agent/README.md`; stage the Task 7 files by name and commit `Add sandbox tools generated from OpenAPI`.

### Task 8: Agent loop, AG-UI endpoint, run logging and image

**Files:** Create `agent/src/spe_agent/{agent,app,runlog,__main__}.py`, `agent/tests/test_app.py`, `agent/Dockerfile`, `agent/.dockerignore`, `agent/README.md`.

**Interfaces:** `create_app(config, secrets, model_override=None, sandbox_client=None)` allows offline tests; production loads configuration from `SPE_AGENT_CONFIG` (default `/etc/spe-agent/agent.yaml`). Expose `GET /healthz` and `POST /agent` on port 8100.

- [ ] **Step 1: Resolve integration details before coding.** Inspect the installed Pydantic AI version for `AGUIAdapter.dispatch_request`, schema tools, `FunctionModel`, streaming events and `UsageLimits`. Inspect the pinned Open WebUI source for system-prompt ordering and parameter conversion. Record source URLs/commit ids and findings in `agent/README.md`; do not infer parity from similar tool names. Confirm the configured Anthropic model exists before any paid call; if unavailable, report that blocker instead of silently substituting a model.

- [ ] **Step 2: Build lifecycle and readiness.** Validate config/secrets immediately. Start sandbox discovery in a background retry task with bounded delay; do not block uvicorn startup. Return 503 from health and authenticated agent requests until tools and prompts are ready. Authenticate before readiness checks so unauthorized requests always get 401. Recover after sandbox startup/restart without restarting the agent; cancel background work and close clients on shutdown. Test `test_unready_sandbox_gives_503_then_recovers` and a failure after initial readiness.

- [ ] **Step 3: Build the loop.** Select the configured model provider, assemble prompts in the verified order, register allowed tools, and pass all three per-run usage limits. Use AG-UI's history conversion for each request; never share mutable conversation history across callers. Reject unsupported configuration and non-positive caps. Preserve typed tool call/result history on later turns.

- [ ] **Step 4: Implement streaming and errors.** Dispatch through the adapter. A valid run emits `RUN_STARTED`, tool events, text and exactly one terminal event. Provider/tool-budget failures produce a sanitized `RUN_ERROR`; never append `RUN_FINISHED` after it. Handle cancellation and client disconnect without leaving an orphan model task. Sandbox background commands may outlive the run; document how the operator stops them.

- [ ] **Step 5: Log runs.** Append one JSONL record per completed, failed or cancelled run, with ids, timestamps, user input, tool arguments/results/durations, answer, usage and error. Redact all three actual key values before writing, including nested fields and errors; keep files private. Avoid logging headers or whole environment mappings. Bound logged tool output. Explain that logs contain player input and scenario canaries and must stay out of git. Check concurrent writes remain separate valid records.

- [ ] **Step 6: Exercise offline.** Script a `FunctionModel` to call a tool and answer. Assert the stream, auth rejection, limits, redaction, cancellation and `test_second_turn_with_tool_history`; also test isolation between two requests. Run the agent tests without real credentials or external services.

- [ ] **Step 7: Package and commit.** Build from the frozen lockfile in Python 3.13, run as a non-root user, expose 8100, and provide a healthcheck that makes no LLM call. Mount config/prompt read-only and the run-log volume writable with the correct uid. Exclude `.env`, caches, logs and local virtualenvs from build context. Run the suite and image health/auth checks with a fake model/sandbox. Commit `Serve the SPE agent over authenticated AG-UI`.

## Phase D — Chat UI and deployment

### Task 9: Minimal CopilotKit chat

**Files:** Create `chat-ui/package.json`, `package-lock.json`, `next.config.mjs`, `tsconfig.json`, `app/layout.tsx`, `app/page.tsx`, `app/api/copilotkit/[[...slug]]/route.ts`, `Dockerfile`, `.dockerignore`, `.gitignore`.

- [ ] **Step 1: Confirm and lock compatible packages.** Check official CopilotKit examples for the chosen runtime and React versions, the Next.js route adapter and `HttpAgent` headers. Pin working versions and commit the lockfile. Use the route shape required by that adapter consistently in the client and server; the draft spec's single-file route is not an API guarantee.
- [ ] **Step 2: Add the server route.** Construct `CopilotRuntime` with agent id `spe`, `AGENT_URL` and the bearer key from server-only environment variables. Keep streaming intact. Neither variable is `NEXT_PUBLIC_*`; the browser must never receive the bearer key in HTML, JS, errors or network responses.
- [ ] **Step 3: Add the page.** Render a full-screen chat and collapsible tool cards with name, arguments, status and bounded results. Show run errors and retain history for a second turn; reload starts fresh. Render tool output as text, not trusted HTML.
- [ ] **Step 4: Build and exercise.** Run `npm ci` and `npm run build`, then use the fake agent from Task 8 to check streamed text, tool cards, errors and a second turn in the browser. Inspect browser assets/network for a disposable test key. Build a Node 24 image running as non-root; give Next.js only the writable paths it needs.
- [ ] **Step 5: Commit.** Stage the listed UI files and commit `Add the CopilotKit chat frontend`.

### Task 10: Ansible AG-UI role and local integration

**Files:** Create `ansible/roles/agui/tasks/main.yml`, `templates/{docker-compose.yml,agent.yaml,agent.env,chat-ui.env}.j2`, `files/agui_smoke.py`; modify `inventory/group_vars/all.yml`, `playbooks/create.yml`, `playbooks/verify.yml`, `roles/verify/tasks/main.yml`, `roles/handoff/{tasks/main.yml,templates/summary.md.j2}`, `instances/dev-local.example.yml`, `ansible/README.md`.

- [ ] **Step 1: Add variables and dispatch.** Add the spec's `spe_agui_*`/`spe_agent_*` variables plus `spe_agent_total_tokens_limit: 400000`. Default `spe_agui_smoke: false` so provisioning never implicitly makes a paid model call. Validate `spe_frontend` against `none|openwebui|agui`, model/provider, positive caps, distinct ports and required keys. Include `agui` only when selected. Render configuration with YAML serialization rather than interpolating arbitrary prompt/model strings into YAML.
- [ ] **Step 2: Build contexts.** Include `sandbox`; sync only tracked application sources and lockfiles using controller SSH arguments. Exclude secrets, `.git`, caches and host dependencies. Derive image tags from context content, including Dockerfiles and locks. Build agent and UI images and reuse the existing terminal env template and sandbox settings. Handle the volume path/uid needed by run logging.
- [ ] **Step 3: Render secrets and compose.** Agent alone receives the LLM key; chat receives agent URL/key; sandbox receives only its existing key/API bases. Use mode 0600 and `no_log` for secret material and secret-bearing checks. Mount config and prompts read-only. Use `ui` and `tools` networks, localhost-only ports 3000/8100 and no sandbox port. Apply the spec's resource/capability settings. The tools network permits reaching the agent; bearer auth is the enforced boundary there.
- [ ] **Step 4: Converge and switch frontends.** Use project `spe-frontend` with orphan removal to replace old services, preserving Open WebUI's data volume. Ensure config changes restart the affected processes even when only a bind-mounted file changed. Preserve equivalent behavior when switching back to Open WebUI. Test both directions using disposable local state and confirm only the selected frontend is running.
- [ ] **Step 5: Share checks.** Put no-cost health, UI, missing/wrong bearer, and key-boundary checks in a reusable task file under `roles/agui/tasks/`; call it from the role and `verify.yml` via the verify role. Inspect sandbox env using its API and compare against real secrets under `no_log`; check sandbox-to-agent unauthenticated requests return 401. Never copy real keys into the sandbox to perform that check.
- [ ] **Step 6: Smoke helper.** Implement `agui_smoke.py` with bearer input through protected environment/file, bounded timeout and SSE parsing. Require a tool call plus `RUN_FINISHED` and reject `RUN_ERROR` or an interrupted stream. Return a nonzero exit code on failure. Run only when `spe_agui_smoke` is explicitly enabled after paid-call approval.
- [ ] **Step 7: Handoff.** Write the agent key to controller `output/<instance>/agent_api_key` with mode 0600 and `no_log`. Generate UI and agent URLs/tunnels from persisted connection details for either provisioning mode, respecting optional SSH key and jump-host args. Local instances need no tunnel. Quote serialized YAML values and shell arguments safely. Do not put keys in the summary or tunnel command.
- [ ] **Step 8: Local deployment.** Set the private dev instance to `agui`, pass the provider key through the operator's protected environment, and run create/verify with smoke disabled. Confirm no Docker daemon changes, both loopback ports, health/auth/key boundary, and a second converge without unnecessary rebuild/restart. After explicit approval, run one smoke and a two-turn chat with visible tool output. Record actual results; a skipped paid check remains pending.
- [ ] **Step 9: Commit.** Review only named source/template/example files and commit `Deploy the AG-UI frontend with Ansible`.

## Phase E — Evaluation and de.NBI handoff

### Task 11: promptfoo client and starter evaluations

**Files:** Create `evals/agui_provider.py`, `evals/asserts.py`, `evals/promptfooconfig.yaml`, `evals/tests/test_agui_provider.py`, `evals/README.md` and an evaluation dependency lockfile.

- [ ] **Step 1: Implement the provider.** Confirm promptfoo's Python provider interface for the installed version. Read `SPE_AGENT_URL` and `SPE_AGENT_API_KEY`, POST valid `RunAgentInput` with unique run/thread ids, and parse SSE incrementally (including multiline data and split network chunks). Accumulate assistant text and tool arguments/results by their ids; return `{output, metadata: {tool_calls, usage}}`. Report HTTP errors, `RUN_ERROR`, timeout, malformed events and missing terminal events as evaluation errors. Never log the auth header.
- [ ] **Step 2: Test without a model.** Use recorded synthetic SSE fixtures for text/tool deltas, multiple tools, error terminals, truncated streams and history. Run `python -m pytest evals/tests -q` in the pinned eval environment.
- [ ] **Step 3: Write deterministic assertions.** Cover registered workflow ids from the handoff, a tool request to TRS, TLS-bypass flags in shell arguments, refusal to download run outputs, and the environment/key probe. Inspect both answer and tool results. Read secret comparison values locally in assertions; never interpolate them into prompts, model-grader inputs, reports or committed config. Explain that checking `-k`/`--insecure` is a regression assertion, not a complete TLS policy proof.
- [ ] **Step 4: Document and run.** Document tunnel setup, private key-file loading, pinned promptfoo invocation, report location and cleanup. Ignore generated reports because they may contain canaries. Specify the number of cases and that this makes paid model calls; obtain approval before the first real evaluation. Report failures individually rather than weakening assertions to obtain a pass.
- [ ] **Step 5: Commit.** Commit the provider, fixtures, assertions, suite and instructions as `Add direct AG-UI evaluations`.

### Task 12: First de.NBI deployment on an existing VM

**Files:** Create `ansible/instances/denbi.example.yml`; update `ansible/README.md` with the deployment procedure and observed results.

- [ ] **Step 1: Prepare a portable template.** Use `spe_provision: existing`, `spe_existing_host: null`, `spe_existing_api_ip: null`, explicit SSH args, dummy data, `wes-drs-smoke`, `spe_frontend: agui`, `openai_compatible`, the existing de.NBI model setting and smoke disabled. Leave seed and keys unset. A real copy is ignored and private.
- [ ] **Step 2: Select and inspect the target.** Use knowledge record 0005's host table as historical evidence. The controller `spe-ga4gh-api-2` already hosts a hand-run stack and is unsuitable for a default install. `agent-service-1` also has an existing frontend: free port 443 alone does not authorize replacing it. Obtain the operator's target choice and explicit replacement authorization if needed. Inspect once using the working SSH config; stop on a connection failure. Confirm marker, stack/frontend/data paths, ports, Docker ownership, disk and private API address. Do not modify any occupied host merely to make preflight pass.
- [ ] **Step 3: Prepare the controller.** Generate dummy data where Ansible runs; the inspected `/data-share` was empty. Confirm rsync follows the same ProxyJump settings. Supply the de.NBI key outside git and choose whether Docker is managed based on the target's actual ownership. Do not assume the old development VM address or filesystem layout applies here.
- [ ] **Step 4: Deploy and verify.** Run create and verify with smoke disabled; require successful recaps and health/auth/key-boundary checks. Re-run to check convergence. Use an SSH tunnel to view the UI. After paid-call approval, run one smoke, a two-turn chat and the starter evals against the de.NBI model. Record provider/model and fixture versions so results are not compared directly with the Anthropic development run.
- [ ] **Step 5: Handoff and commit.** Document tunnel, key-file location, log access, restart, evaluation and reset commands without credential values. Record only observations actually made, and list any deferred checks with reasons. Commit the example and documentation as `Document the existing-VM de.NBI deployment`.

### Task 13: Reconcile the design and close implementation

**Files:** Update `docs/specs/2026-10-15-agui-frontend-design.md`, this plan, `agent/README.md`, `evals/README.md`, `ansible/README.md` as relevant.

- [ ] **Step 1: Reconcile the spec.** Record verified package/API versions and source references, prompt ordering, tool-schema differences, total token limit, smoke default, readiness recovery, route shape and read-only filesystem findings. Correct the stale claim that the controller has the base dataset and the suggestion to commit a real dev seed. Distinguish proposed settings from observed results. Do not describe per-run limits as aggregate spend enforcement; portal/user budgets remain deferred.
- [ ] **Step 2: Check acceptance evidence.** Require the matrix below to be satisfied or explicitly marked pending. Do not mark deployment or paid evaluations complete based only on a build. Keep failures, provider differences and remaining limitations visible.
- [ ] **Step 3: Commit and link.** Commit documentation in this repository. In the parent biohackathon repository, update knowledge record 0005 with links to this plan and the implementation commit actually inspected, preserving its proposed status unless acceptance is explicitly agreed. Commit that record separately. Do not push either repository.

## Acceptance evidence

| Outcome | Evidence required | Task |
|---|---|---|
| Existing-VM lifecycle | Create, repeat converge, ownership refusal, confirmed reset/recreate; Docker settings unchanged when unmanaged | 1–4 |
| Baseline retained | Open WebUI templates render identically with synthetic inputs; shared sandbox builds; frontend switching preserves its data | 5, 10 |
| Agent behavior | Offline schema, streaming, history, limit, readiness, logging and cancellation tests pass | 6–8 |
| Credential boundary | Unauthorized requests fail; no LLM/agent key in sandbox env or browser; private/redacted logs and handoff | 8–10 |
| User experience | UI build, visible tool execution, streamed answer, second turn and visible errors | 9–10 |
| Evaluation | Offline SSE tests plus separately reported real-model suite results | 11 |
| Deployment | Named existing VM, successful create/verify/re-run, tunnel and approved smoke evidence | 12 |
| Reproducibility | Committed locks/examples/docs, inspected source commits, clean staged review, no secrets | 13 |

Finishing this document does not satisfy this matrix. Fleet profiles, public exposure/authentication, portal flags, egress controls and the red/blue loop remain sub-projects 2–4 of record 0005.
