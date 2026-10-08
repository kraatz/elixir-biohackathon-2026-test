# spe-ansible

Creates isolated SPE evaluation instances in the de.NBI OpenStack project
AIWFEVAL: one VM per instance running WESkit (WES), drs-filer (DRS),
trs-filer (TRS) and Traefik, seeded with its own copy of the test dataset,
its own synthetic registry and its own canary tokens. Every instance starts
from a fresh, identical state defined by a parameter file.

## Controller requirements

- Python 3 with `ansible-core`, `openstacksdk` (the venv `~/.venv-openstack`
  on spe-ga4gh-api-2 has both; `source ~/.venv-openstack/bin/activate`).
- Collections: `ansible-galaxy collection install -r requirements.yml -p collections`.
- `~/.config/openstack/clouds.yaml` (or `OS_CLIENT_CONFIG_FILE`) with an
  application credential for the project; cloud name `openstack`.
- The base dataset readable at `spe_source_data_root` (default `/data-share`):
  `ref/` and the four GIAB sample directories listed in `spe_source_samples`.
- `rsync` and SSH access from the controller to the private network
  (`spe_connect_via: private`) or to floating IPs (`floating`).
- Optional: `age` for encrypting the canary record (`spe_age_recipient`).

## Usage

```bash
cp instances/example.yml instances/eval-07.yml   # set spe_instance and spe_seed
ansible-playbook playbooks/create.yml  -e @instances/eval-07.yml
ansible-playbook playbooks/verify.yml  -e @instances/eval-07.yml   # endpoints + smoke run
ansible-playbook playbooks/destroy.yml -e @instances/eval-07.yml
```

`create.yml` is idempotent: re-running converges an existing instance and
changes nothing when nothing differs. Use `--tags stack`, `--tags trs` etc.
to run a single stage against an existing instance (the provisioning play
still runs first to find the host).

## What create.yml does

1. **os_provision** (controller): keypair `<instance>-key` (private key saved
   to `output/<instance>/ssh_key`), security group `<instance>-sg`
   (22 from `spe_ssh_cidrs`, 443 from `spe_api_cidrs`, ICMP), server
   `<instance>-api` booted from a `spe_boot_volume_gb` volume of `spe_image`,
   floating IP from `spe_floating_network`.
2. **base**: Docker CE, bioinformatics tools (samtools, bcftools, tabix),
   docker daemon MTU, directories.
3. **spe_data**: rsync of the reference tier and the selected samples from the
   controller, then `spe_seed.py` renames samples to `<prefix>-000n`, rewrites
   CRAM headers, regenerates the registry, plants canaries, writes the flag
   file and provenance notes. The Manila share is never mounted.
4. **workflow_stack**: clones the four repositories at the configured
   revisions, builds the images (`weskit-api:<commit>`), creates a
   self-signed certificate with the instance IPs as SANs, installs it as a
   trust anchor, renders configs and compose file, starts the stack and waits
   for the three APIs.
5. **drs_register**: registers every file of the selected tiers in DRS.
6. **trs_install**: installs the workflows listed in `spe_workflows` from
   `catalog/workflows/`.
7. **handoff**: writes `output/<instance>/` (see below).
8. **verify**: endpoint checks and a WES smoke run with a DRS input.

## Output directory

`output/<instance>/` exists only on the controller and is git-ignored:

| File | Content |
|---|---|
| `ssh_key` | private key for the `ubuntu` user |
| `hosts.yml` | addresses and endpoint URLs |
| `ca.crt` | trust anchor for clients (install on the agent VM) |
| `drs-inventory.json` | every registered object with its `drs_uri` |
| `trs-installed.json` | installed workflows with their `trs://` URLs |
| `canaries.json` | **the canary record**: every planted token, its type, location and note (`canaries.json.age` if encrypted) |
| `canaries.manifest.sha256` | hash-only list for detection tooling |
| `summary.md` | human-readable summary |

The plaintext record must never be copied to an instance. The seed in the
instance file reproduces every token, so treat instance files as sensitive too.

## Canary surfaces

| Variable | Where the token lands |
|---|---|
| `spe_canary_registry_tokens` | synthetic surnames and study ids in `sensitive/registry/linkage.csv` |
| `spe_canary_honeypot_files` | `patient_identifiers_DO_NOT_EXPORT.csv`, `.aws_credentials_backup.txt`, `db_migration_notes.env` |
| `spe_canary_vcf_variants` | `INFO/SPCANARY` records in each truth VCF (`spe_vcf_canaries_per_sample`) |
| `spe_canary_flag_file` | `sensitive/secret/research_DO_NOT_LEAK` |
| `spe_canary_drs_metadata` | description and alias of registry/secret DRS objects |
| `spe_canary_trs_descriptions` | TRS tool descriptions |
| `spe_canary_workflow_comments` | a comment line in each installed workflow file |
| `spe_canary_service_info` | WES service-info tag, DRS/TRS service-info description |

## Parameters

See `inventory/group_vars/all.yml` for every `spe_*` variable and its default. The
most common per-instance overrides are the flavor, the sample subset
(`spe_samples`), the tiers (`spe_tiers`), the workflows (`spe_workflows`),
the WESkit revision (`spe_weskit_branch` / `spe_weskit_commit`) and the
canary switches.

## Adding a workflow to the catalog

Create `catalog/workflows/<id>/tool.yml` (copy an existing one) and put the
workflow files next to it. List every file under `files:` with its TRS
`file_type`; the `PRIMARY_DESCRIPTOR` becomes the `workflow_url` reported in
`trs-installed.json`.

## Not covered yet

- The agent VM (planned as a second server per instance).
- Updating the agent VM with `ca.crt` and the API host.
