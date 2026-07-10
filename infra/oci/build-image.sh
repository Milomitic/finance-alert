#!/usr/bin/env bash
# Build the app image for the A1 VM (linux/arm64!) and save it as a tarball that
# deploy-k3s.sh imports straight into k3s — no registry needed (OCIR is 403 on
# the free tier). The VM is Ampere ARM, so we cross-build via Docker Desktop's
# QEMU emulation; it's slow (several minutes) but needs no arm hardware.
#
# Run from anywhere in the repo:  bash infra/oci/build-image.sh [tag]
set -euo pipefail
TAG="${1:-oci}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT="$SCRIPT_DIR/finance-alert_arm64.tar"

command -v docker >/dev/null || { echo "docker not found — start Docker Desktop"; exit 1; }
docker info >/dev/null 2>&1  || { echo "docker daemon unreachable"; exit 1; }

echo "building finance-alert:$TAG for linux/arm64 (emulated — be patient)…"
docker buildx build --platform linux/arm64 -t "finance-alert:$TAG" --load "$REPO_ROOT"

echo "saving → $OUT"
docker save "finance-alert:$TAG" -o "$OUT"
echo "done. size: $(du -h "$OUT" | cut -f1). Next: bash infra/oci/deploy-k3s.sh"
