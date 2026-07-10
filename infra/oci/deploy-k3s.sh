#!/usr/bin/env bash
# Deploy the app onto the k3s VM, once the A1 bot (a1-retry.sh) has brought the
# VM up. Registry-free flow:
#   1. read the VM's public IP from terraform state
#   2. wait for cloud-init to finish installing k3s (/opt/k3s/ready)
#   3. import the arm64 image tar into k3s' containerd
#   4. pull a working kubeconfig off the box
#   5. helm upgrade --install with the OCI overlay + a fresh random SECRET_KEY
#
# Prereqs: the VM is RUNNING, ~/.ssh/oci_finance_alert exists, `helm` on PATH
# (installed for M2), Docker running (terraform + the image build run in it),
# and infra/oci/finance-alert_arm64.tar built (bash infra/oci/build-image.sh).
#
# Run:  bash infra/oci/deploy-k3s.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$REPO_ROOT/infra/terraform"
TAR="$SCRIPT_DIR/finance-alert_arm64.tar"
KUBECONFIG_FILE="$REPO_ROOT/kubeconfig-oci"
KEY="$HOME/.ssh/oci_finance_alert"
CHART="$REPO_ROOT/charts/finance-alert"

tf() {
  MSYS_NO_PATHCONV=1 docker run --rm -v "$TF_DIR:/wd" -w /wd \
    -v "$HOME/.oci:/root/.oci:ro" "hashicorp/terraform:1.9" "$@"
}

# ── Preflight ────────────────────────────────────────────────────────────────
command -v helm >/dev/null || { echo "helm not found — install it (winget install Helm.Helm)"; exit 1; }
[ -f "$KEY" ]  || { echo "missing SSH key $KEY"; exit 1; }
[ -f "$TAR" ]  || { echo "missing $TAR — run: bash infra/oci/build-image.sh"; exit 1; }

IP="$(tf output -raw ingress_public_ip 2>/dev/null | tr -d '\r')"
[ -n "$IP" ] || { echo "no ingress_public_ip in terraform state — is the VM up? (bash infra/oci/status.sh)"; exit 1; }
echo "VM public IP: $IP"

SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 opc@$IP"

# ── 1. wait for k3s to finish installing ─────────────────────────────────────
echo "waiting for k3s to come up on the VM (cloud-init)…"
until $SSH 'test -f /opt/k3s/ready' 2>/dev/null; do echo "  …not ready yet, retrying in 15s"; sleep 15; done
echo "k3s is ready."

# ── 2. import the image into k3s containerd ──────────────────────────────────
# Skip the (large) upload if the tar is already on the VM intact — makes retries
# cheap. sudo needs the FULL path: Oracle Linux's secure_path excludes
# /usr/local/bin where k3s lives.
LOCAL_SZ=$(stat -c %s "$TAR" 2>/dev/null || echo 0)
REMOTE_SZ=$($SSH 'stat -c %s /tmp/app.tar 2>/dev/null' 2>/dev/null | tr -d "\r" || echo 0)
if [ "$LOCAL_SZ" = "$REMOTE_SZ" ] && [ "$LOCAL_SZ" != 0 ]; then
  echo "image already on the VM (${LOCAL_SZ} bytes) — skipping upload"
else
  echo "uploading the app image (~595M, a few minutes)…"
  scp -i "$KEY" -o StrictHostKeyChecking=accept-new "$TAR" "opc@$IP:/tmp/app.tar"
fi
echo "importing image into k3s containerd…"
$SSH 'sudo /usr/local/bin/k3s ctr images import /tmp/app.tar'

# ── 3. fetch a remote-usable kubeconfig ──────────────────────────────────────
echo "fetching kubeconfig → $KUBECONFIG_FILE"
$SSH 'sudo cat /etc/rancher/k3s/k3s.yaml' | sed "s#127.0.0.1#$IP#" > "$KUBECONFIG_FILE"
export KUBECONFIG="$KUBECONFIG_FILE"

# ── 4. deploy with a fresh random SECRET_KEY ─────────────────────────────────
SECRET="$(openssl rand -hex 32)"
echo "helm upgrade --install…"
helm upgrade --install finance-alert "$CHART" \
  -f "$CHART/values-oci.yaml" \
  --set secret.secretKey="$SECRET" \
  --namespace finance-alert --create-namespace \
  --wait --timeout 6m

echo
echo "✅ deployed. App: http://$IP/   (allowlisted to your IP)"
echo "   kubectl:  export KUBECONFIG=$KUBECONFIG_FILE"
