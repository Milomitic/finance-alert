#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# A1 capacity-acquisition bot for OCI Always-Free OKE.
#
# The problem: Ampere A1 Always-Free capacity is scarce; `terraform apply` can
# "succeed" (the node pool resource is created) while the underlying VMs never
# launch because there's no host capacity. OCI exposes NO "is capacity free?"
# API — the only signal is *attempting to launch*. Capacity frees up in short,
# unpredictable windows.
#
# What this does: on a loop, it (1) ensures the node pool exists via Terraform,
# (2) waits a grace period, (3) checks whether the pool has ACTIVE nodes, and
# (4) if not, DESTROYS + recreates just the node pool on the next pass — a fresh
# launch attempt each cycle, which is how you catch a capacity window. Cluster,
# VCN, storage etc. are created ONCE and left alone (no capacity constraint).
# On success it optionally pings Telegram and exits.
#
# FULLY CONTAINERISED — you install NOTHING but Docker. Terraform and the OCI
# CLI both run in throwaway containers; auth comes from terraform.tfvars + the
# API private key you drop at ~/.oci/oci_api_key.pem. No host CLIs, no
# ~/.oci/config with host-specific paths (the classic container gotcha).
#
# Prerequisites (see docs/cloud/RUN-A1-BOT.md):
#   - Docker Desktop running
#   - infra/terraform/terraform.tfvars filled in (OCIDs + fingerprint)
#   - ~/.oci/oci_api_key.pem = your API private key
#
# Run from anywhere:  bash infra/oci/a1-retry.sh
# Tunables via env :  INTERVAL=240 GRACE=210 MAX_HOURS=48 bash infra/oci/a1-retry.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

# ── Config (env-overridable) ─────────────────────────────────────────────────
INTERVAL="${INTERVAL:-180}"                 # base seconds between attempts
JITTER="${JITTER:-60}"                      # random 0..JITTER added, avoids lockstep
MAX_HOURS="${MAX_HOURS:-72}"                # hard stop after this many hours
GRACE="${GRACE:-210}"                       # seconds to let nodes try to launch post-apply
TF_VERSION="${TF_VERSION:-1.9}"
OCI_CLI_IMAGE="${OCI_CLI_IMAGE:-ghcr.io/oracle/oci-cli:latest}"
NOTIFY="${NOTIFY:-1}"                        # 1 = Telegram ping on success (if configured)
HOST_OCI_DIR="${HOST_OCI_DIR:-$HOME/.oci}"   # holds oci_api_key.pem, mounted read-only

# ── Resolve paths (absolute; the repo root is this script's ../../) ──────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$REPO_ROOT/infra/terraform"
TFVARS="$TF_DIR/terraform.tfvars"
LOG="$SCRIPT_DIR/a1-retry.log"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# Read one value out of terraform.tfvars (HCL `name = "value"` lines).
tfvar() {
  local v
  v=$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$TFVARS" 2>/dev/null | head -1 | cut -d= -f2-)
  v="${v%%#*}"                       # strip trailing comment
  echo "$v" | tr -d '"' | xargs      # strip quotes + trim whitespace
}

# MSYS_NO_PATHCONV stops Git-Bash mangling container mount paths on Windows;
# ignored on Linux/macOS.
tf() {
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "$TF_DIR:/wd" -w /wd \
    -v "$HOST_OCI_DIR:/root/.oci:ro" \
    "hashicorp/terraform:$TF_VERSION" "$@"
}
# OCI CLI in a container; auth entirely via env (overrides any config file).
ocicli() {
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "$HOST_OCI_DIR:/root/.oci:ro" \
    -e OCI_CLI_AUTH=api_key \
    -e "OCI_CLI_TENANCY=$TENANCY" \
    -e "OCI_CLI_USER=$USER_OCID" \
    -e "OCI_CLI_FINGERPRINT=$FINGERPRINT" \
    -e OCI_CLI_KEY_FILE=/root/.oci/oci_api_key.pem \
    -e "OCI_CLI_REGION=$REGION" \
    "$OCI_CLI_IMAGE" "$@"
}

# ── Preflight ────────────────────────────────────────────────────────────────
command -v docker >/dev/null           || { echo "docker not found — install Docker Desktop"; exit 1; }
docker info >/dev/null 2>&1            || { echo "docker daemon unreachable — start Docker Desktop"; exit 1; }
[ -f "$TFVARS" ]                       || { echo "missing $TFVARS — cp terraform.tfvars.example terraform.tfvars and fill it"; exit 1; }
[ -f "$HOST_OCI_DIR/oci_api_key.pem" ] || { echo "missing $HOST_OCI_DIR/oci_api_key.pem — save your API private key there"; exit 1; }

TENANCY="$(tfvar tenancy_ocid)"
USER_OCID="$(tfvar user_ocid)"
FINGERPRINT="$(tfvar fingerprint)"
REGION="$(tfvar region)"
for v in TENANCY USER_OCID FINGERPRINT REGION; do
  [ -n "${!v}" ] || { echo "missing '$v' in $TFVARS — fill tenancy_ocid/user_ocid/fingerprint/region"; exit 1; }
done

log "verifying OCI auth (first run also pulls the oci-cli image)…"
ocicli iam region list >/dev/null 2>>"$LOG" \
  || { log "OCI auth FAILED — check the OCIDs/fingerprint in tfvars and ~/.oci/oci_api_key.pem"; exit 1; }
log "auth OK"

notify() {
  [ "$NOTIFY" = "1" ] || return 0
  local env_file="$REPO_ROOT/backend/.env" tok chat
  [ -f "$env_file" ] || return 0
  tok=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$env_file" | cut -d= -f2- | tr -d '"'"'"' \r')
  chat=$(grep -E '^TELEGRAM_CHAT_ID='  "$env_file" | cut -d= -f2- | tr -d '"'"'"' \r')
  [ -n "$tok" ] && [ -n "$chat" ] || return 0
  curl -s -o /dev/null "https://api.telegram.org/bot${tok}/sendMessage" \
    --data-urlencode "chat_id=${chat}" --data-urlencode "text=$1" || true
}

# Count ACTIVE nodes in the pool (the authoritative check — Terraform can't see
# per-node lifecycle state).
active_nodes() {
  ocicli ce node-pool get --node-pool-id "$1" \
    --query 'length(data.nodes[?"lifecycle-state"==`ACTIVE`])' --raw-output 2>/dev/null \
    | tr -cd '0-9' || echo 0
}

# ── Bootstrap: create everything once (nodes may fail on capacity) ───────────
log "init + one-time apply of cluster/network/storage"
tf init  -input=false >>"$LOG" 2>&1
tf apply -auto-approve -input=false >>"$LOG" 2>&1 \
  || log "initial apply returned non-zero (likely node capacity) — entering retry loop"

POOL_ID="$(tf output -raw node_pool_id 2>/dev/null | tr -d '\r')"
DESIRED="$(tfvar node_count)"; DESIRED="${DESIRED:-2}"
[ -n "$POOL_ID" ] || { log "no node_pool_id output — the cluster/pool did not get created; check $LOG"; exit 1; }
log "node pool $POOL_ID · target ACTIVE nodes: $DESIRED"

# ── Retry loop ───────────────────────────────────────────────────────────────
DEADLINE=$(( $(date +%s) + MAX_HOURS*3600 ))
attempt=0
while :; do
  attempt=$((attempt+1))
  [ "$(date +%s)" -ge "$DEADLINE" ] && { log "gave up after ${MAX_HOURS}h / ${attempt} attempts"; notify "❌ A1 bot: gave up after ${MAX_HOURS}h"; exit 2; }

  log "attempt #$attempt — waiting ${GRACE}s for nodes to launch…"
  sleep "$GRACE"

  n="$(active_nodes "$POOL_ID")"; n="${n:-0}"
  if [ "$n" -ge "$DESIRED" ] 2>/dev/null; then
    log "🎉 SUCCESS — $n/$DESIRED nodes ACTIVE"
    notify "🎉 A1 acquired: $n/$DESIRED OKE nodes ACTIVE. Next: terraform output kubeconfig_command"
    exit 0
  fi

  log "only $n/$DESIRED ACTIVE — recreating node pool to force a fresh launch attempt"
  tf destroy -target=oci_containerengine_node_pool.this -auto-approve -input=false >>"$LOG" 2>&1 \
    || log "node-pool destroy returned non-zero (continuing)"
  tf apply   -target=oci_containerengine_node_pool.this -auto-approve -input=false >>"$LOG" 2>&1 \
    || log "node-pool apply returned non-zero (likely capacity) — will retry"
  POOL_ID="$(tf output -raw node_pool_id 2>/dev/null | tr -d '\r')"   # recreation mints a new OCID

  back=$(( INTERVAL + RANDOM % (JITTER+1) ))
  log "backing off ${back}s before next cycle"
  sleep "$back"
done
