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
# VCN, storage etc. are created ONCE and left alone (they have no capacity
# constraint). On success it optionally pings Telegram and exits.
#
# Prerequisites (see docs/cloud/OCI-SETUP.md):
#   - Docker running (Terraform runs in a container — no host install needed)
#   - OCI CLI installed + `~/.oci/config` working (`oci iam region list` returns JSON)
#   - infra/terraform/terraform.tfvars filled in
#
# Run from the repo root:  bash infra/oci/a1-retry.sh
# Tunables via env, e.g.:  INTERVAL=240 MAX_HOURS=48 bash infra/oci/a1-retry.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

# ── Config (env-overridable) ─────────────────────────────────────────────────
INTERVAL="${INTERVAL:-180}"            # base seconds between attempts
JITTER="${JITTER:-60}"                 # random 0..JITTER added, avoids lockstep
MAX_HOURS="${MAX_HOURS:-72}"           # hard stop after this many hours
GRACE="${GRACE:-210}"                  # seconds to let nodes try to launch post-apply
TF_VERSION="${TF_VERSION:-1.9}"
NOTIFY="${NOTIFY:-1}"                  # 1 = Telegram ping on success (if configured)

# ── Resolve paths (absolute; the repo root is this script's ../../) ──────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$REPO_ROOT/infra/terraform"
LOG="$SCRIPT_DIR/a1-retry.log"

# MSYS_NO_PATHCONV stops Git-Bash from mangling the container mount paths on
# Windows. On Linux/macOS it's simply ignored.
tf() {
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "$TF_DIR:/wd" -w /wd \
    -v "$HOME/.oci:/root/.oci:ro" \
    "hashicorp/terraform:$TF_VERSION" "$@"
}

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# ── Preflight ────────────────────────────────────────────────────────────────
command -v docker >/dev/null || { echo "docker not found"; exit 1; }
command -v oci    >/dev/null || { echo "OCI CLI not found — install + oci setup config"; exit 1; }
[ -f "$TF_DIR/terraform.tfvars" ] || { echo "missing $TF_DIR/terraform.tfvars"; exit 1; }
oci iam region list >/dev/null 2>&1 || { echo "OCI auth failed — check ~/.oci/config"; exit 1; }

notify() {
  [ "$NOTIFY" = "1" ] || return 0
  # Reuse the app's Telegram bot if configured in backend/.env.
  local env_file="$REPO_ROOT/backend/.env" tok chat
  [ -f "$env_file" ] || return 0
  tok=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$env_file" | cut -d= -f2- | tr -d '"'"'"' \r')
  chat=$(grep -E '^TELEGRAM_CHAT_ID='  "$env_file" | cut -d= -f2- | tr -d '"'"'"' \r')
  [ -n "$tok" ] && [ -n "$chat" ] || return 0
  curl -s -o /dev/null "https://api.telegram.org/bot${tok}/sendMessage" \
    --data-urlencode "chat_id=${chat}" --data-urlencode "text=$1" || true
}

# Count ACTIVE nodes in the pool via OCI CLI (the authoritative check —
# Terraform can't see per-node lifecycle state).
active_nodes() {
  local pool_id="$1"
  oci ce node-pool get --node-pool-id "$pool_id" \
    --query 'length(data.nodes[?"lifecycle-state"==`ACTIVE`])' --raw-output 2>/dev/null || echo 0
}

# ── Bootstrap: create everything EXCEPT retryable nodes once ──────────────────
log "init + one-time apply of cluster/network/storage (node pool included; nodes may fail on capacity)"
tf init -input=false >>"$LOG" 2>&1
tf apply -auto-approve -input=false >>"$LOG" 2>&1 || log "initial apply returned non-zero (likely node capacity) — entering retry loop"

POOL_ID="$(tf output -raw node_pool_id 2>/dev/null | tr -d '\r')"
DESIRED="$(grep -E '^\s*node_count' "$TF_DIR/terraform.tfvars" 2>/dev/null | grep -oE '[0-9]+' || echo 2)"
[ -n "$POOL_ID" ] || { log "no node_pool_id output — the cluster/pool did not get created; check $LOG"; exit 1; }
log "node pool $POOL_ID · target ACTIVE nodes: $DESIRED"

# ── Retry loop ───────────────────────────────────────────────────────────────
DEADLINE=$(( $(date +%s) + MAX_HOURS*3600 ))
attempt=0
while :; do
  attempt=$((attempt+1))
  now=$(date +%s)
  [ "$now" -ge "$DEADLINE" ] && { log "gave up after ${MAX_HOURS}h / ${attempt} attempts"; notify "❌ A1 bot: gave up after ${MAX_HOURS}h"; exit 2; }

  log "attempt #$attempt — waiting ${GRACE}s for nodes to launch…"
  sleep "$GRACE"

  n=$(active_nodes "$POOL_ID")
  if [ "${n:-0}" -ge "$DESIRED" ]; then
    log "🎉 SUCCESS — $n/$DESIRED nodes ACTIVE"
    notify "🎉 A1 acquired: $n/$DESIRED nodes ACTIVE on OKE. Run: terraform output kubeconfig_command"
    exit 0
  fi

  log "only ${n:-0}/${DESIRED} ACTIVE — recreating node pool to force a fresh launch attempt"
  tf destroy -target=oci_containerengine_node_pool.this -auto-approve -input=false >>"$LOG" 2>&1 \
    || log "node-pool destroy returned non-zero (continuing)"
  tf apply   -target=oci_containerengine_node_pool.this -auto-approve -input=false >>"$LOG" 2>&1 \
    || log "node-pool apply returned non-zero (likely capacity) — will retry"
  # Refresh the pool id (recreation mints a new OCID).
  POOL_ID="$(tf output -raw node_pool_id 2>/dev/null | tr -d '\r')"

  back=$(( INTERVAL + RANDOM % (JITTER+1) ))
  log "backing off ${back}s before next cycle"
  sleep "$back"
done
