# GitOps + CI/CD (M5) — how deploys work now

## The loop

```
git push origin cloud
   │
   ▼
GitHub Actions (.github/workflows/ci.yml)
   ├─ backend:  ruff fatal-gate + pytest (1371, network-guarded)
   ├─ frontend: tsc + vite build
   ├─ audit:    pip-audit + npm audit (advisory, never blocks)
   └─ image:    buildx linux/arm64 → ghcr.io/milomitic/finance-alert:<sha>
                → trivy (advisory) → bump job rewrites image.tag in
                  charts/finance-alert/values-oci.yaml  ("[skip ci]" commit)
   │
   ▼
ArgoCD (running INSIDE the k3s cluster, ns argocd)
   polls this public repo (targetRevision cloud, path charts/finance-alert),
   renders the chart with values-oci.yaml, and auto-syncs the diff
   (automated: selfHeal on, prune off).
   │
   ▼
k3s applies it → StatefulSet rolls to the new image → app live.
```

Deploys are **pull-based** on purpose: the k3s API (6443) is NSG-allowlisted to
the owner's IP, so CI can't push to the cluster. ArgoCD reaches OUT from inside.
This is the standard, safer GitOps posture.

## Bootstrap (already done, one-time)

```bash
export KUBECONFIG=$PWD/kubeconfig-oci
# durable Secret (SECRET_KEY + admin bcrypt hash) — NOT chart-managed, never in git
kubectl -n finance-alert create secret generic finance-alert-prod \
  --from-literal=SECRET_KEY=<random> --from-literal=ADMIN_PASSWORD_HASH=<bcrypt>
# ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd --server-side -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -f infra/gitops/finance-alert-app.yaml   # the Application CR
```

## ⚠️ The one open item: make the GHCR package PUBLIC

CI pushes the image to `ghcr.io/milomitic/finance-alert`, but the package is
**private** by default and the local `gh` token lacks the `packages` scope, so
it couldn't be flipped automatically. Consequences:

- The node currently runs the image because it was **retagged into containerd**
  by hand (`k3s ctr images tag docker.io/library/finance-alert:oci
  ghcr.io/milomitic/finance-alert:<sha>`), and `pullPolicy: IfNotPresent` means
  the kubelet uses that local copy instead of pulling.
- **A push to `cloud` before the package is public will bump the tag to a new
  `<sha>` the node has never seen → `IfNotPresent` tries to pull → private GHCR
  → `ImagePullBackOff` → the pod can't start.**

**Fix (30 seconds, one-time):** GitHub → your profile → Packages →
`finance-alert` → Package settings → Change visibility → **Public**. After that
the whole loop is hands-off: a `cloud` push builds a new `<sha>`, the node
pulls it anonymously from public GHCR, no manual retag ever again.

Until then, either don't push to `cloud`, or retag the node image to the new
`<sha>` before ArgoCD syncs:
```bash
NEWSHA=$(git show origin/cloud:charts/finance-alert/values-oci.yaml | sed -n 's/^  tag: "\(.*\)"/\1/p')
ssh -i ~/.ssh/oci_finance_alert opc@<VM_IP> \
  "sudo /usr/local/bin/k3s ctr images tag docker.io/library/finance-alert:oci ghcr.io/milomitic/finance-alert:$NEWSHA"
```

## Operational notes

- **Never** put the literal skip-ci marker in a commit message you want CI to
  run — GitHub honours it anywhere in the head commit. (It cost one silent
  no-run here.) Conversely, a docs-only commit that must NOT trigger a
  tag-bump/rollout should carry it.
- The old Helm release secrets (`sh.helm.release.v1.finance-alert.*`) and the
  chart-created `finance-alert-finance-alert-secret` are now inert (ArgoCD is
  the deployer, the pod reads `finance-alert-prod`). Harmless to leave; delete
  for hygiene once you're confident.
- `SECRET_KEY` moved to `finance-alert-prod` (a different value than the old
  chart Secret) → existing browser sessions were invalidated at cutover; log
  in again.
- ArgoCD UI: `kubectl -n argocd port-forward svc/argocd-server 8080:443` then
  https://localhost:8080 (initial admin password:
  `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d`).
