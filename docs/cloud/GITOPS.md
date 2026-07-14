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

## Registry: GHCR is public → fully hands-off ✅

The `ghcr.io/milomitic/finance-alert` package is **public**, so the k3s node
pulls each new `<sha>` anonymously (`pullPolicy: IfNotPresent` → pull once per
immutable sha, cached after). Nothing manual: a `cloud` push builds the image,
the bump job points `values-oci.yaml` at the new sha, ArgoCD syncs, the kubelet
pulls it from public GHCR. Verified end-to-end on 2026-07-15.

> Historical fallback (only if the package is ever made private again): seed the
> node image directly and rely on `IfNotPresent` —
> `k3s ctr images tag docker.io/library/finance-alert:oci ghcr.io/milomitic/finance-alert:<sha>`.

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
