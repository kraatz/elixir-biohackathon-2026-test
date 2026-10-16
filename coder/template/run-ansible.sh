#!/usr/bin/env bash
# Run one SPE playbook with the vars Terraform passes in SPE_VARS_JSON.
# The vars contain the agent token, so they go through a private temp file
# instead of the command line. Output is piped through cat because Ansible
# refuses the non-blocking stdout the provisioner hands it.
set -euo pipefail
playbook=$1
vars=$(mktemp)
trap 'rm -f "$vars"' EXIT
chmod 600 "$vars"
printf '%s' "$SPE_VARS_JSON" > "$vars"
cd "$SPE_ANSIBLE_DIR"
export ANSIBLE_PYTHON_INTERPRETER="$(command -v python3)"
export ANSIBLE_FORCE_COLOR=0
ansible-playbook "playbooks/$playbook" -e "@$vars" </dev/null 2>&1 | cat
