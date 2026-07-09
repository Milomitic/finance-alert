#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# A1 capacity-acquisition bot — brings up the Always-Free Ampere A1 VM that runs
# k3s (see infra/terraform/compute.tf).
#
# The problem: A1 Always-Free capacity is scarce; a launch either succeeds or
# returns "Out of host capacity". OCI exposes NO "is capacity free?" API — the
# only signal is *attempting to launch*, and capacity appears in short,
# unpredictable windows. `terraform apply` for a compute instance waits for the
# VM to reach RUNNING and returns non-zero on a capacity failure, so the whole
# job is: loop apply until it lands, backing off between tries. Everything else
# (VCN/subnet/NSG/bucket) is created on the first pass and left alone.
#
# FULLY CONTAINERISED — you install NOTHING but Docker. Terraform and the OCI
# CLI run in throwaway containers; auth comes from terraform.tfvars + the API
# private key at ~/.oci/oci_api_key.pem.
#
# Prerequisites (see docs/cloud/RUN-A1-BOT.md):
#   - Docker Desktop running
#   - infra/terraform/terraform.tfvars filled in (OCIDs + fingerprint)
#   - ~/.oci/oci_api_key.pem = your API private key
#
# Run:  bash infra/oci/a1-retry.sh
# Tune: INTERVAL=240 MAX_HOURS=48 bash infra/oci/a1-retry.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

# ── Config (env-overridable) ─────────────────────────────────────────────────
INTERVAL="${INTERVAL:-180}"                 # base seconds between attempts
JITTER="${JITTER:-60}"                      # random 0..JITTER added, avoids lockstep
MAX_HOURS="${MAX_HOURS:-72}"                # hard stop after this many hours
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
APPLY_OUT="$SCRIPT_DIR/.last-apply.out"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# Read one value out of terraform.tfvars (HCL `name = "value"` lines).
tfvar() {
  local v
  v=$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$TFVARS" 2>/dev/null | head -1 | cut -d= -f2-)
  v="${v%%#*}"
  echo "$v" | tr -d '"' | xargs
}

# MSYS_NO_PATHCONV stops Git-Bash mangling container mount paths on Windows.
tf() {
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "$TF_DIR:/wd" -w /wd \
    -v "$HOST_OCI_DIR:/root/.oci:ro" \
    "hashicorp/terraform:$TF_VERSION" "$@"
}
# OCI CLI in a container; --user 0:0 because the image runs as uid 1000 which
# can't read the mounted /root/.oci (dir mode 700). Only used for the auth probe.
ocicli() {
  MSYS_NO_PATHCONV=1 docker run --rm \
    --entrypoint oci --user 0:0 \
    -v "$HOST_OCI_DIR:/root/.oci:ro" \
    -e OCI_CLI_AUTH=api_key \
    -e "OCI_CLI_TENANCY=$TENANCY" \
    -e "OCI_CLI_USER=$USER_OCID" \
    -e "OCI_CLI_FINGERPRINT=$FINGERPRINT" \
    -e OCI_CLI_KEY_FILE=/root/.oci/oci_api_key.pem \
    -e "OCI_CLI_REGION=$REGION" \
    -e OCI_CLI_SUPPRESS_FILE_PERMISSIONS_WARNING=True \
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
  [ -n "${!v}" ] || { echo "missing '$v' in $TFVARS"; exit 1; }
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

# ── Bootstrap ────────────────────────────────────────────────────────────────
log "terraform init"
tf init -input=false >>"$LOG" 2>&1

# ── Retry loop: apply until the A1 VM lands ──────────────────────────────────
DEADLINE=$(( $(date +%s) + MAX_HOURS*3600 ))
attempt=0
while :; do
  attempt=$((attempt+1))
  [ "$(date +%s)" -ge "$DEADLINE" ] && { log "gave up after ${MAX_HOURS}h / ${attempt} attempts"; notify "❌ A1 bot: gave up after ${MAX_HOURS}h"; exit 2; }

  log "attempt #$attempt — terraform apply (creates + awaits the A1 VM)…"
  tf apply -auto-approve -input=false >"$APPLY_OUT" 2>&1
  rc=$?
  cat "$APPLY_OUT" >> "$LOG"

  if [ "$rc" -eq 0 ]; then
    IP="$(tf output -raw ingress_public_ip 2>/dev/null | tr -d '\r')"
    log "🎉 SUCCESS — A1 VM is RUNNING at ${IP:-?}. k3s installs via cloud-init (~2-3 min)."
    notify "🎉 A1 VM up at ${IP:-?}. Next: terraform output fetch_kubeconfig, then kubectl get nodes."
    exit 0
  fi

  if grep -qiE "out of host capacity|out of capacity|no capacity|too ?many ?requests|429|throttl" "$APPLY_OUT"; then
    back=$(( INTERVAL + RANDOM % (JITTER+1) ))
    log "A1 capacity unavailable — retrying in ${back}s"
    sleep "$back"
  else
    log "non-capacity apply error — stopping (inspect $LOG). This usually means a config/limit issue, not capacity."
    tail -25 "$APPLY_OUT" | sed -E 's/\x1b\[[0-9;]*m//g' | tee -a "$LOG"
    notify "❌ A1 bot stopped: non-capacity error on apply. Check the log."
    exit 1
  fi
done
