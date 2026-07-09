# Cloud / Platform Roadmap — finance-alert on OCI

> **Goal.** Take a working local-first app (FastAPI + React + SQLite) and evolve
> it into a production, cloud-native deployment on **Oracle Cloud Infrastructure
> Always Free**, as a portfolio project demonstrating IaC, Kubernetes, GitOps,
> polyglot persistence and observability — with every architectural choice
> defensible in an interview.
>
> **Non-goal.** Minimal ops. The app is single-user; parts of this stack are
> deliberately "over-built" for the learning/portfolio value. That trade-off is
> explicit, not accidental.

This document is the **source of truth** for the cloud effort. It lives on the
`cloud` branch; `master` stays the untouched local-first app. The tag
`localhost-stable-2026-07-09` is the permanent rollback point for the
SQLite/`just up` world.

---

## Guiding principles

1. **One repo, additive, env-gated.** No forked "cloud copy". Everything new
   (`Dockerfile`, `compose.yaml`, `charts/`, `infra/`, `.github/`) is additive;
   the app selects behaviour by env/config (12-factor), so the same artifact
   runs locally and in-cluster. `master`'s `just up` flow never breaks.
2. **The data is safe by construction.** `backend/data/app.db` is gitignored and
   lives only on the dev machine. Nothing in the cluster ever touches it; the
   cluster runs its own database. A dated DB snapshot + the nightly `VACUUM INTO`
   backup are the data rollback.
3. **Right tool per workload (polyglot persistence).** Each datastore earns its
   place by solving a problem the others handle badly — never "because CV".
4. **Security is a first-class milestone, not an afterthought.** Least-privilege
   DB roles, audit trail, NetworkPolicies, no publicly-exposed datastores,
   TLS end-to-end, secrets never in git.
5. **Every milestone is a reviewable PR** with a short "decisions & trade-offs"
   note — that narrative is the portfolio.

---

## Target architecture (end state)

```
                    Internet (IP allowlist @ OCI NSG)
                              │  :443
                    ┌─────────▼──────────┐
                    │  Ingress + TLS     │  ingress-nginx / Traefik
                    │  cert-manager (LE) │  DNS-01 challenge
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  FastAPI (app pod) │  Deployment, N replicas
                    │  serves built SPA  │
                    └──┬───────┬─────┬───┘
             reads/writes │  cache │   │ scrape/analytics
                    ┌─────▼──┐ ┌──▼───┐ │
                    │Postgres│ │Valkey│ │
                    │  (CNPG │ │(K/V, │ │
                    │operator│ │throt-│ │
                    │ + jsonb│ │ tle) │ │
                    │+pgvec  │ └──────┘ │
                    │+Timesc)│          │
                    └───┬────┘          │
              WAL/backup │              │
                    ┌────▼─────────┐    │
                    │ OCI Object   │    │
                    │ Storage      │    │
                    └──────────────┘    │
                              observability │
                    ┌─────────────────────▼────────────┐
                    │ Prometheus  Grafana  Loki         │
                    │ (metrics)   (dash)   (logs)       │
                    └───────────────────────────────────┘

Provisioned by Terraform (VCN/NSG/OKE/IP/bucket) · GitOps by ArgoCD · CI by GitHub Actions
```

**Datastore responsibilities (polyglot persistence):**

| Store | Owns | Why not the others |
|---|---|---|
| **PostgreSQL** | Relational core (stocks, ohlcv, alerts, outcomes, 13F, positions, scores) + JSON blobs via `jsonb` (snapshots, fetch_cache) | The app is join- and aggregation-heavy; `jsonb` gives document flexibility without losing joins |
| **Postgres + `pgvector`** | News-embedding semantic search | Zero new infra (extension); covers the emerging "AI data" line |
| **Postgres + TimescaleDB** *(optional)* | `ohlcv_daily` as a hypertable | 2.4M time-ordered rows are a natural fit; still just Postgres |
| **Valkey** | Shared cache (L1 fundamentals/news/quote) + login-throttle state | On multi-replica K8s the in-process dict resets per pod and isn't shared — needs an external K/V |
| **Prometheus** | Metrics (app + cluster) | Time-series metrics ≠ relational |
| **Loki** | Centralised logs | Log aggregation / retention ≠ the app DB |

---

## Milestones

Each is a self-contained PR into `cloud`. Order matters: earlier ones unblock later ones.

### M0 — Foundation ✅ (done)
- Safety tag `localhost-stable-2026-07-09`; branch `cloud`; this ROADMAP.
- **Outcome:** rollback point established, work isolated from `master`.

### M1 — Containerisation
- Multi-stage `Dockerfile` (frontend build → python `uv` runtime serving the built `dist`).
- `compose.yaml` for local parity (app only; SQLite volume-mounted).
- `.dockerignore`; app reads all config from env (verify `settings` coverage).
- **Portfolio signal:** reproducible build, 12-factor config.
- **Local impact:** none — `just up` untouched; compose is an alternative.

### M2 — Kubernetes locally + SQLite StatefulSet
- Helm chart (`charts/finance-alert`): Deployment for the app, **StatefulSet + PVC (RWO, 1 replica) for SQLite**.
- Run on a local cluster (kind/minikube) to validate manifests offline.
- Liveness/readiness probes on `/api/health`.
- **Portfolio signal:** K8s primitives, the honest "single-writer on a PVC" pattern (defensible compromise).
- **This is the first "cluster green end-to-end" win.**

### M3 — OCI infra as code (Terraform)
- `infra/` Terraform: VCN, public subnet, **NSG with IP allowlist**, Internet Gateway, **reserved public IP**, **OKE Basic cluster** (control plane free), **Ampere A1 node pool** (Always Free), Object Storage bucket, OCIR repo.
- State backend on Object Storage (or OCI Resource Manager).
- **Portfolio signal:** IaC — the headline DevOps skill.
- **Gotchas encoded here:** dual firewall (NSG + host), A1 capacity, reserved-IP-before-DNS.

### M4 — Ingress + TLS + security headers
- `ingress-nginx` (or Traefik) + **cert-manager** with **Let's Encrypt DNS-01** (HTTP-01 fails behind the IP allowlist — documented).
- Domain A-record → reserved IP; HTTPS redirect; **HSTS + CSP + security headers**.
- App: `TrustedHostMiddleware`, `SECRET_KEY` fail-fast in prod, `is_dev=False` ⇒ `Secure` cookie.
- **Portfolio signal:** networking, automated certs, app-layer hardening.

### M5 — GitOps (ArgoCD) + CI/CD
- **ArgoCD** watching `charts/` — declarative, self-healing deploys.
- **GitHub Actions:** tests (1300+, network-guarded) + build → **Trivy** (image CVEs) + `pip-audit`/`npm audit` → push to OCIR.
- **Renovate/Dependabot** for dependency PRs.
- **Portfolio signal:** GitOps + DevSecOps pipeline.

### M6 — Observability
- **Prometheus** (app `/metrics` via `prometheus-fastapi-instrumentator` + cluster metrics), **Grafana** dashboards, **Loki** for logs (the Salute log stream centralised).
- Alertmanager → the existing Telegram surface (reuse `notify_health_transition`).
- **Portfolio signal:** the canonical SRE stack, on real data.

### M7 — **PostgreSQL migration** (the headline milestone)
- **CloudNativePG operator**: Postgres cluster (StatefulSet + PVC under the hood), **WAL archiving to Object Storage** (barman), verified restore.
- App changes (all env-gated, SQLite stays default until cutover):
  - `json_extract(…)` → `jsonb ->>` (abstract behind a dialect helper).
  - `VACUUM INTO` backup job → `pg_dump`/barman.
  - Drop SQLite-isms: `PRAGMA`, `busy_timeout`, WAL; retire the `scan_lock`
    single-writer mutex (Postgres handles concurrent writes).
  - `timestamptz` cleans up the naive-datetime UTC-retag hacks.
  - Tests → **testcontainers-postgres** (retire the SQLite-dialect divergence risk); local dev → compose Postgres. Keep `localhost-stable` as the SQLite fallback.
- Data migration via **pgloader** (2.4M rows — trivial).
- **Security layer (this is where the ⭐⭐⭐ "relational" line pays off):**
  **pgaudit**, SCRAM auth, TLS app↔DB, **least-privilege roles** (app ≠ migration ≠ read-only-for-Grafana), NetworkPolicy so only the app pod reaches Postgres.
- **Portfolio signal:** *"migrated stateful data from SQLite to an operator-managed Postgres on K8s, with WAL archiving, verified restore, and least-privilege + audit"* — the strongest single line on the CV.

### M8 — Polyglot persistence & extensions
- **Valkey** (Deployment/StatefulSet): move the L1 cache + login-throttle state off in-process → shared. NetworkPolicy + auth; never a public port.
- **pgvector** extension: embed news per ticker → semantic "similar news" search.
- **TimescaleDB** *(optional)*: `ohlcv_daily` → hypertable.
- **Portfolio signal:** motivated polyglot persistence + AI-data (pgvector) + time-series, each defensible.

### M9 — Production hardening & docs
- **systemd/node hardening** (if any host-level bits), `fail2ban` on SSH, unattended-upgrades.
- **DR runbook**: restore Postgres from Object Storage; recreate cluster from Terraform.
- **README/architecture doc** with the diagram + decisions log — the portfolio front page.
- Optional: **DNS-01 renewal** verification, backup-restore drill in CI.

---

## Cost summary (all $0 on OCI Always Free except the domain)

| Component | Free? |
|---|---|
| OKE Basic control plane + Ampere A1 nodes (≤4 OCPU/24GB) | ✅ Always Free |
| Block Volume (≤200GB, encrypted at rest) | ✅ |
| Object Storage (10GB — backups/WAL) | ✅ |
| VCN/NSG/IGW/reserved IP (attached) | ✅ |
| OCIR (within Object Storage allowance) | ✅ |
| Terraform / Kubernetes / Helm / ArgoCD / cert-manager / Prometheus / Grafana / Loki / Valkey / Postgres+CNPG / pgvector / Timescale | ✅ open-source, self-hosted |
| GitHub Actions | ✅ (unlimited on public repos) |
| **Domain registration** | ❌ ~€10/yr (or free subdomain: DuckDNS / Cloudflare-managed) |
| Managed Postgres on OCI (NOT used — self-hosted instead) | 💰 paid |

**Watch-outs:** Ampere A1 capacity can be scarce in popular regions; Oracle
reclaims idle Always Free instances (keep the cluster minimally active);
Let's Encrypt HTTP-01 is blocked by the IP allowlist → use DNS-01.

---

## Status

| Milestone | State |
|---|---|
| M0 Foundation | ✅ done |
| M1 Containerisation | ✅ done — image builds, container serves `/api/health` + SPA, non-root, isolated DB (host `app.db` untouched). Fixed a Windows-only lockfile → cross-platform superset for `npm ci`. |
| M2 K8s + SQLite StatefulSet | ✅ done — kind cluster + Helm chart (StatefulSet 1-replica owning an embedded-SQLite PVC, non-root securityContext + fsGroup, startup/readiness/liveness on `/api/health`). Verified: pod Ready via Service, and **data survives a pod delete** on the re-bound PVC. Corrected the roadmap's own wording — with embedded SQLite the app IS the StatefulSet (no separate DB pod); that split happens at M7 with Postgres. |
| M3 Terraform / infra | 🟡 **applied against a live account; k3s VM pending A1 capacity.** Pivoted OKE → self-managed **k3s on an A1 VM**: a pure Always-Free tenancy pins OKE limits to **0** (`cluster-count`/`node-count`, verified live) so managed K8s is impossible without PAYG, but standalone A1 compute (2 OCPU/12 GB here) is allowed. Network + NSG (SSH/6443/443/80 allowlisted) + Object Storage bucket **created**; the A1 VM (`compute.tf`, Oracle-Linux-aarch64, cloud-init k3s) is being retried by `infra/oci/a1-retry.sh` until Milan frees A1 capacity. OCIR gated off (`403 FREE_TIER_NOT_SUPPORTED`). Also cleared two leftover console-wizard VCNs (quota was 2/2) and bumped a stale K8s pin. See `docs/cloud/RUN-A1-BOT.md`. |
| M4 Ingress + TLS + hardening | ⬜ |
| M5 GitOps + CI/CD | ⬜ |
| M6 Observability | ⬜ |
| M7 Postgres migration | ⬜ |
| M8 Polyglot (Valkey/pgvector/Timescale) | ⬜ |
| M9 Prod hardening + docs | ⬜ |
