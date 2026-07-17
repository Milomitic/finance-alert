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

## Architecture (as deployed — this is reality, not a plan)

```
                         Internet
                            │
   :80  0.0.0.0/0 ──────────┤        :443  IP-allowlist @ OCI NSG
   ACME challenge ONLY      │        (everything real lives here)
   (404 for everything else)│
                    ┌───────▼────────────┐
                    │ Traefik (bundled   │  cert-manager + Let's Encrypt
                    │ with k3s)          │  HTTP-01 → 80-225-80-141.sslip.io
                    └───────┬────────────┘
                            │
                    ┌───────▼────────────┐
                    │ FastAPI (app pod)  │  StatefulSet, 1 replica
                    │ + built React SPA  │  APScheduler runs IN-PROCESS
                    └───┬────────────┬───┘
         reads/writes   │            │ /metrics
                  ┌─────▼──┐         │
                  │Postgres│ CloudNativePG operator · TLS enforced
                  │  `pg`  │ non-superuser app role · pgaudit (ddl,role)
                  │ +jsonb │ NetworkPolicy
                  └───┬────┘
      WAL (continuous)│
      + daily base    │
                  ┌───▼──────────┐
                  │ OCI Object   │  barman-cloud over the S3-compat API
                  │ Storage      │  restore DRILL PASSED (data == live)
                  └──────────────┘
                            observability
                    ┌───────────────────────────────────┐
                    │ Prometheus · Grafana · Loki       │
                    │ Alertmanager → Telegram           │
                    └───────────────────────────────────┘

Terraform (VCN/NSG/A1 VM/bucket) · self-managed k3s · ArgoCD GitOps · GitHub Actions CI
```

> Deviations from the original plan, and why: **k3s not OKE** (a pure Always-Free
> tenancy pins OKE cluster/node limits to 0); **HTTP-01 not DNS-01** (the host is
> `sslip.io`, a public wildcard service whose zone we do not control — so :80 is
> open to the world for the challenge, and *only* the challenge); **1 replica not
> N** (APScheduler runs in-process, so a second replica would duplicate every
> scan — multi-replica needs leader election first).

**Datastore responsibilities:**

| Store | Owns | Why not the others |
|---|---|---|
| **PostgreSQL** | Relational core (stocks, ohlcv, alerts, outcomes, 13F, positions, scores) + JSON blobs via `jsonb` (snapshots, fetch_cache) | The app is join- and aggregation-heavy; `jsonb` gives document flexibility without losing joins |
| **Prometheus** | Metrics (app + cluster) | Time-series metrics ≠ relational |
| **Loki** | Centralised logs | Log aggregation / retention ≠ the app DB |
| **OCI Object Storage** | Postgres base backups + WAL | Durability outside the node's disk |

> **Polyglot persistence (Valkey / pgvector / TimescaleDB) was considered and
> dropped — see the note after the milestones.** Keeping the store list honest
> matters more than making it look impressive.

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

### ~~M8 — Polyglot persistence & extensions~~ — **DROPPED (2026-07-17)**

Cut deliberately, not forgotten. Each of the three was re-examined against the
system as actually built, and none survived:

- **Valkey** (shared cache + login-throttle state) — **YAGNI**. Its whole premise
  was "on multi-replica K8s the in-process dict isn't shared". The app runs **one
  replica** and cannot trivially run more (APScheduler is in-process; a second
  replica would duplicate every scan). Solving a problem the deployment does not
  have would add a component, a NetworkPolicy, an auth secret and a failure mode,
  in exchange for nothing.
- **pgvector** (news-embedding semantic search) — needs an **embedding source**:
  a paid API, or a local model on a node whose RAM is already shared by app +
  Postgres + Prometheus + Loki. The extension is the easy part; the cost is not.
- **TimescaleDB** (`ohlcv_daily` as a hypertable) — **not in the CloudNativePG
  image**, so it needs a custom Postgres image to build and maintain. 2.4M rows
  are also simply not enough to hurt: the queries that matter are already indexed
  and fast.

This mirrors the rule the engine side of this project already follows (see
CLAUDE.md: no confirmation-count bonus, no pillar reweighting, no factor
adjustments — all rejected because the studies showed no edge). **Infrastructure
deserves the same bar as scoring: build it when there is evidence it is needed.**
A CV line about "polyglot persistence" that exists only to be a CV line is worth
less than being able to explain why you *didn't* build it.

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
| Terraform / k3s / Helm / ArgoCD / cert-manager / Prometheus / Grafana / Loki / Postgres+CNPG | ✅ open-source, self-hosted |
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
| M3 Terraform / infra | ✅ **done — live on OCI.** Pivoted OKE → self-managed **k3s on an A1 VM** (pure Always-Free pins OKE `cluster-count`/`node-count` to **0**; standalone A1 compute — 2 OCPU/12 GB — is allowed). Terraform-applied against the real account: VCN + NSG (SSH/6443/443/80 allowlisted) + Object Storage + the A1 VM (`compute.tf`, Oracle-Linux-aarch64, cloud-init installs k3s v1.36.2, Traefik, local-path). A1 capacity caught by `infra/oci/a1-retry.sh` on attempt #6. Cleared two leftover wizard VCNs (quota 2/2), bumped a stale K8s pin, gated OCIR off (`403 FREE_TIER`). See `RUN-A1-BOT.md`. |
| M2b App deployed on cloud k3s | ✅ **done — app is LIVE.** arm64 image cross-built (buildx) → imported registry-free (`k3s ctr images import`) → Helm chart deployed with the OCI overlay (`values-oci.yaml`: local-path PVC, Traefik ingress, random SECRET_KEY). `GET http://<vm-ip>/api/health` → `200 {"status":"ok"}` and the SPA serves. Scripts: `infra/oci/build-image.sh`, `deploy-k3s.sh`, `status.sh`. **HTTP only — TLS + a domain are M4.** |
| M4 Ingress + TLS + hardening | ✅ **DONE — real HTTPS, no domain purchased.** Unblocked by busting a myth: an earlier session concluded the ISP's RPZ blocks nip.io/sslip.io, which was an **nslookup suffix-search artifact** (Windows appends `wind3.hub` to non-FQDN queries; even `google.com` "fails" that way — always test with a trailing dot). `80-225-80-141.sslip.io` resolves to the VM, so **cert-manager v1.21** (GitOps) issues a real **Let's Encrypt** cert (staging first to protect prod rate limits, then prod: `issuer=CN=YR2`, TLS verify=0, auto-renew 2026-09-14). NSG `:80` opened to 0.0.0.0/0 — ACME validators have rotating IPs — but it serves **only** the challenge: app and Grafana are `websecure`-only on `:443`, which stays IP-allowlisted (verified: `http://…/api/health` and `http://…/grafana/login` both **404**). Finally `APP_ENV=production` → the **session cookie is `Secure`** (the security review's top finding; impossible before TLS since a Secure cookie never traverses plain HTTP) — `is_dev` was verified to have exactly ONE consumer, and two tests now assert the flag both ways. ⚠️ Caught + fixed a regression this introduced: opening `:80` briefly exposed the path-based Grafana that had been relying on the NSG allowlist; it is now websecure-only with its own cert, fixed declaratively in the values (a kubectl patch would have been undone by the next helm upgrade). App: **https://80-225-80-141.sslip.io/** |
| M5 GitOps + CI/CD | ✅ **done — full loop live.** CI (GitHub Actions): ruff fatal-gate + pytest 1371, tsc+vite, pip-audit/npm audit (advisory), **arm64 image → GHCR** (GHA cache), trivy (advisory), **tag-bump** commit to `values-oci.yaml`. **ArgoCD** on k3s watches the repo and **auto-synced/adopted** the release (Synced/Healthy) → pod runs the git-pinned `ghcr…:<sha>` reading the durable `finance-alert-prod` Secret; `selfHeal` reverts drift (verified). Deploys are pull-based (NSG blocks CI→6443). Verified E2E: health 200, DB persisted, login OK. **GHCR package is public** → the node pulls each new sha anonymously; the loop is fully hands-off (verified 2026-07-15). See `docs/cloud/GITOPS.md`. Backlog: ruff full-config adoption. |
| M6 Observability | ✅ **done — live.** kube-prometheus-stack (Prometheus 3d + Grafana + Alertmanager + node-exporter/kube-state-metrics) + Loki/promtail (72h logs), sized for the shared 12 GB VM (node ~46%). App `/metrics` via prometheus-fastapi-instrumentator, scraped by a PodMonitor (14 targets all up). Grafana at `http://<ip>/grafana` (path-based; ISP DNS blocks nip.io). Alertmanager→Telegram (reuses the app bot; test alert delivered). Datasources: Prometheus/Loki/Alertmanager. See `docs/cloud/OBSERVABILITY.md`. |
| M7 Postgres migration | ✅ **DONE — the live app runs on operator-managed Postgres.** P1 (app portability) done. `json_text()` @compiles helper (SQLite `json_extract` ↔ Postgres `jsonb ->>`) replaces the raw `json_extract` in alert/confluence/sectors; the nightly `VACUUM INTO` backup no-ops on a non-SQLite engine (Postgres PITR is the cluster's job); `psycopg[binary]` added to runtime deps (aarch64 wheels). Proven portable without a cutover: all **25 tables compile to Postgres DDL**, `json_text` SQL asserted for **both** dialects (`test_db_json_dialect`), and a real **`postgres:16` CI lane** (`backend-postgres`, guarded by `TEST_DATABASE_URL`, off the deploy needs-chain) `create_all`'s the whole schema + runs `json_text` on live Postgres. **P2 (CloudNativePG) core done:** operator 1.30 (chart 0.29.0, arm64) via a GitOps ArgoCD Application in `cnpg-system`; a single-instance PG16 `Cluster` (`bootstrap.initdb` → DB `finance_alert` owned by the non-superuser role `fa_app`; CNPG auto-generates the `pg-app` Secret + TLS certs). Verified live: cluster **healthy 1/1**, and an app-labeled pod authenticates as `fa_app` over TCP **with SSL** (`pg_stat_ssl.ssl=t`) through the `pg-rw` service. NetworkPolicy applied — with a MEASURED k3s/kube-router caveat: pod/namespaceSelectors don't match ClusterIP-service traffic (only direct-pod-IP), source IP is preserved, so the app path is allowed via `ipBlock` on the pod CIDR; per-pod isolation over the service path would need Calico (P5). ArgoCD Synced/Healthy on `cnpg-operator` + `postgres-cluster`. **P2 fully done** — WAL archiving + a daily base backup run to the private `finance-alert-backups` OCI bucket (S3-compat, barman-cloud); base backup `completed`, `firstRecoverabilityPoint` set. Needed the OCI fix `AWS_*_CHECKSUM_CALCULATION=WHEN_REQUIRED` (boto3≥1.36 chunked encoding → OCI `NotImplemented`). Credential = an OCI Customer Secret Key in Secret `pg-wal-s3` (out-of-band, not in git). **P3 data migration DONE** — `app/scripts/migrate_sqlite_to_pg.py` (idempotent, re-runnable at cutover) copied **2,804,018 rows / 25 tables with full parity** from a VACUUM INTO snapshot into Postgres (run via port-forward so the compute stayed off the live app pod); sequences reset, alembic stamped `5f67045e4500`. Integrity spot-checked on migrated data (json_text tone counts, numeric cast, boolean 900F/99T). **P4 CUTOVER DONE — the live app now runs on Postgres.** Mechanism is a single gated values flag (`postgres.enabled`): the chart wires `DATABASE_URL` from the operator-managed `pg-app` Secret via secretKeyRef, and `config.normalize_db_url()` rewrites CNPG's bare `postgresql://` to `+psycopg` (psycopg2 isn't installed). Zero-data-loss sequence: scale app to 0 (writes halted) → final migration IN-CLUSTER from the freed PVC (throwaway pod on the app image) → 2,804,018 rows re-loaded at full parity → flip flag + scale to 1. Verified live: health ok, alembic logs `Context impl PostgresqlImpl`, `pg_stat_activity` shows the app pod connected, and `ohlcv_daily` grew past the migrated count — proving the app READS AND WRITES Postgres. SPA 200, auth 401. **Rollback** = flip the flag back; the SQLite file on the PVC is untouched (the migration only READ it). Node at 57% mem with app + PG + observability. **P5 hardening DONE — every claim verified, not asserted.** (1) **Restore drill**: bootstrapped a throwaway cluster purely from the Object Storage backup + WAL replay — it came up healthy with data IDENTICAL to live (999/4304/2,434,321/306,358), schema, alembic and the non-superuser `fa_app` role intact; then deleted. This is the *verified* in "verified restore". (2) **require-TLS**: CNPG's default pg_hba ends with a permissive `host … scram-sha-256` that also accepts cleartext; added `hostssl … scram-sha-256` + `hostnossl … reject` (user rules precede the default). Probed: `sslmode=disable` → `FATAL: pg_hba.conf rejects connection … no encryption`, `sslmode=require` → ok. App unaffected (already TLSv1.3). (3) **pgaudit** `ddl,role` → Postgres log → Loki → Grafana; a DDL probe was captured in full. Deliberately NOT `write` — a scan writes millions of ohlcv rows and would flood the 85%-full disk. (4) Grafana read-only role **deliberately skipped (YAGNI)**: no Grafana Postgres datasource exists, so it would be an unused credential; add it together with the datasource if DB dashboards are ever wanted. |
| M9 Prod hardening + docs | 🔨 **node patching + DR runbook done.** **The VM had NEVER been patched**: a week after provisioning it carried **185 pending security advisories (6 Critical, 119 Important)** — the stock Oracle Linux image ships a backlog and OCI patches nothing for you. No alert, no log, no symptom: you only find it if you look. Applied supervised (`dnf update --security`, app/pods/node unaffected, zero restarts) and installed **dnf-automatic** (security-only, `apply_updates=yes`, **`reboot = never`** — a single-node cluster rebooting unannounced IS an outage), declared in cloud-init so a rebuilt node is born patched. Then a **deliberate, supervised reboot** to activate the new kernel (6.12.0-204.92.4.3), which doubled as a **resilience test — PASSED**: VM back in ~60s, **all 28 pods self-healed in ~75s**, Postgres PVC + data byte-identical (999/4394/2,435,192), TLS cert intact, app resumed scanning on its own. **Security advisories: 185 → 0.** Also reclaimed ~2 GB (80%→74%) of SQLite snapshots made obsolete by the M7 cutover. DR runbook: `RUNBOOK-postgres-dr.md`. **Remaining:** ARCHITECTURE.md is stale (still describes the SQLite/pre-cloud app) — the portfolio front page still needs rewriting. |
