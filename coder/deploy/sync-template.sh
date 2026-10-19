#!/usr/bin/env bash
# Pull the repo and push the Coder template when it changed. Run by
# sperange-sync.timer on the portal VM, so configs merged to the branch show up
# in the portal within minutes, without GitHub needing access to the VM.
#
# Environment (from /etc/sperange/sync.env):
#   SPE_REPO_DIR       repo checkout, e.g. /home/ubuntu/sperange
#   SPE_BRANCH         branch to follow, e.g. main
#   SPE_TEMPLATE_NAME  Coder template name, e.g. spe-testbed
#   SPE_AGENT_URL      Coder URL as seen from the SPE VMs, e.g. http://10.0.2.50:7080
#   CODER_URL, CODER_SESSION_TOKEN   Coder API access (long-lived token)
set -euo pipefail
cd "$SPE_REPO_DIR"
git fetch --quiet origin "$SPE_BRANCH"
git checkout --quiet "$SPE_BRANCH"
git merge --quiet --ff-only "origin/$SPE_BRANCH"

head=$(git rev-parse HEAD)
state="$SPE_REPO_DIR/.git/sperange-pushed"
if [[ -f $state && $(cat "$state") == "$head" && ${1:-} != --force ]]; then
  exit 0
fi

coder templates push "$SPE_TEMPLATE_NAME" \
  --directory coder/template \
  --variable "spe_ansible_dir=$SPE_REPO_DIR/ansible" \
  --variable "coder_agent_url=$SPE_AGENT_URL" \
  --name "$(git rev-parse --short HEAD)" \
  --message "$(git log -1 --format=%s)" \
  --yes
echo "$head" > "$state"
