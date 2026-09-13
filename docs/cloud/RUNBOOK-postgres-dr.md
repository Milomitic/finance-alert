# Runbook — PostgreSQL disaster recovery (M7/M9)

**The restore path below was executed and verified end-to-end on 2026-07-16 and
again on 2026-09-09**: a throwaway cluster was bootstrapped from *nothing but
the Object Storage backup* and came up with data identical to live. This is not
a theoretical procedure. See the drill log at the bottom for what each run
measured.

> Supersedes the Object-Storage half of `RUNBOOK-db-migration.md`, which is now
> the **SQLite-era / localhost** procedure. The cloud app runs on Postgres.

---

## What the backup actually is

| Piece | Where | Cadence |
|---|---|---|
| Base backups | `s3://finance-alert-backups/` (private OCI bucket, versioned) | `ScheduledBackup pg-daily` @ 02:00 + on demand |
| WAL segments | same bucket, gzip | continuous (`archive_command`) |
| Retention | `ObjectStore.spec.retentionPolicy: 30d` | plugin prunes |

Together they give **point-in-time recovery**: any instant covered by a base
backup plus the WAL that follows it.

Credentials live in Secret **`pg-wal-s3`** (an OCI *Customer Secret Key* — an
S3-compatible access key + secret). **Never in git.** Recreate with:

```bash
kubectl --kubeconfig=./kubeconfig-oci -n finance-alert create secret generic pg-wal-s3 --from-literal=ACCESS_KEY_ID='…' --from-literal=SECRET_ACCESS_KEY='…'
```

Keep it on **one line** — a multi-line paste with `\` continuations breaks in
Git Bash and silently creates an EMPTY secret in the wrong namespace.

---

## Health check — are backups actually working?

```bash
export KC=./kubeconfig-oci

# 1) WAL archiving live? Expect ContinuousArchiving=True
kubectl --kubeconfig=$KC get cluster pg -n finance-alert \
  -o jsonpath='{range .status.conditions[*]}{.type}={.status}({.reason}){"\n"}{end}'

# 2) A recoverable point exists? Both fields must be set.
kubectl --kubeconfig=$KC get cluster pg -n finance-alert \
  -o jsonpath='lastBackup={.status.lastSuccessfulBackup} first={.status.firstRecoverabilityPoint}{"\n"}'
```

`firstRecoverabilityPoint` is read back **from the bucket** — if it is set, the
objects really are there.

Do **not** be fooled by a hand-run `barman-cloud-backup-list` via `kubectl exec`:
it fails with `Unable to locate credentials` because the operator injects the S3
env only into its own barman invocations. That is a false negative, not a broken
backup.

Take an on-demand base backup before any risky change:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Backup
metadata: {name: pre-change, namespace: finance-alert}
spec:
  cluster: {name: pg}
  method: plugin
  pluginConfiguration:
    name: barman-cloud.cloudnative-pg.io
```

---

## Restore

**Always restore into a NEW cluster.** Never point recovery at the live one: the
original stays intact as the fallback, and you can compare before switching.

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: pg-restore
  namespace: finance-alert
spec:
  instances: 1
  imageName: ghcr.io/cloudnative-pg/postgresql:16
  env:                      # MANDATORY on OCI — see Gotcha 1
    - {name: AWS_REQUEST_CHECKSUM_CALCULATION, value: WHEN_REQUIRED}
    - {name: AWS_RESPONSE_CHECKSUM_VALIDATION, value: WHEN_REQUIRED}
  storage: {size: 5Gi, storageClass: local-path}
  resources:
    requests: {cpu: 100m, memory: 256Mi}
    limits: {memory: 768Mi}
  bootstrap:
    recovery:
      source: pg-origin
      # Omit recoveryTarget => recover to the LATEST archived WAL.
      # For PITR instead:
      # recoveryTarget: {targetTime: "2026-07-16 09:30:00+00"}
  externalClusters:
    - name: pg-origin
      plugin:
        name: barman-cloud.cloudnative-pg.io
        parameters:
          barmanObjectName: pg-backups
          serverName: pg          # the ORIGIN cluster's name inside the bucket
```

```bash
kubectl --kubeconfig=$KC apply -f pg-restore.yaml
# 'Setting up primary' -> a *-full-recovery-* job runs -> 'Cluster in healthy state'
kubectl --kubeconfig=$KC get cluster pg-restore -n finance-alert -w
```

### Verify before trusting it

```bash
kubectl --kubeconfig=$KC exec pg-restore-1 -n finance-alert -c postgres -- \
  psql -d finance_alert -tAc "select 'stocks='||(select count(*) from stocks)||' alerts='||(select count(*) from alerts)||' ohlcv='||(select count(*) from ohlcv_daily);"

# schema + alembic + role survived?
kubectl --kubeconfig=$KC exec pg-restore-1 -n finance-alert -c postgres -- \
  psql -d finance_alert -tAc "select (select count(*) from information_schema.tables where table_schema='public'), (select version_num from alembic_version), (select rolsuper from pg_roles where rolname='fa_app');"
```

Expect ~26 tables (25 model tables + `alembic_version`) and `fa_app`
**rolsuper=false** — a restore that silently escalates the app role is a failed
restore.

### Promote the restored cluster (real disaster)

The app finds its DB through the Secret named in
`charts/finance-alert/values-oci.yaml` (`postgres.secretName`, default
`pg-app`). To cut over to the restored cluster, point it at `pg-restore-app` and
commit — ArgoCD rolls the app. Scale the app to 0 first if split-brain writes
would matter.

### Break-glass — back to SQLite

Set `postgres.enabled: false` in `values-oci.yaml`. The pre-M7 SQLite file is
still on the app PVC (the migration only ever READ it). **Anything written to
Postgres after the cutover will not be there** — this is a break-glass, not a
data rollback.

---

## The app Secret dies with the node too — recreate it

Restoring Postgres is not enough. The app also needs the **`finance-alert-prod`**
Secret (SECRET_KEY + ADMIN_PASSWORD_HASH + MARKETAUX_API_KEY), which lives ONLY
in the cluster — not in git, not in Terraform. Rebuild it with:

```bash
bash infra/oci/recreate-app-secret.sh          # prompts for the admin password
# or non-interactive:
ADMIN_PASSWORD='…' MARKETAUX_API_KEY='…' bash infra/oci/recreate-app-secret.sh
```

None of the three values is truly lost: SECRET_KEY is random (regenerating it
just re-logs everyone in), ADMIN_PASSWORD_HASH is a bcrypt of a password you
know (the script re-hashes via the app's own code so the cost never drifts), and
MARKETAUX is in your account. The script restarts the app so it re-reads the
Secret. **Verified end-to-end 2026-07-17**: after recreation, login returned 200
with the same password and 401 with a wrong one.

## Gotchas (each one cost real debugging time)

1. **OCI rejects the AWS SDK's default chunked encoding.** boto3 ≥ 1.36 signs
   payloads with streaming/trailing checksums; OCI's S3-compatible API answers
   `NotImplemented: AWS chunked encoding not supported` to **every PutObject**.
   Fix: the two `AWS_*_CHECKSUM_*=WHEN_REQUIRED` env vars above. Symptom: WAL
   archiving *and* base backups fail while everything else looks healthy.
2. **`serverName` is the ORIGIN cluster's name** (`pg`), not the new cluster's —
   barman namespaces objects in the bucket by server name.
3. **In-tree barman is deprecated** (removed in CloudNativePG 1.31). The live
   manifests now target the **Barman Cloud Plugin**; verify the plugin is Healthy
   and run a successful backup before upgrading the operator.
4. **Disk.** The node root volume was ~85% full; a restore adds a second PVC.
   Check free space before starting.
5. **TLS is enforced** (`pg_hba`: `hostssl …` + `hostnossl … reject`). Clients
   must use `sslmode=require` or better; `sslmode=disable` gets
   `FATAL: pg_hba.conf rejects connection … no encryption`.

---

## Drill cadence — AUTOMATED since 2026-09-13

The drill above runs **by itself, every Monday at 04:00 UTC**:
`charts/finance-alert/templates/cronjob-restore-drill.yaml`.

⚠️ It was automated because the previous version of this section said "and
periodically otherwise", and **a cadence that depends on someone remembering is
not a cadence**. The procedure was proven by hand exactly once, in July.

What the CronJob adds over the manual steps below:

- a **pre-flight disk guard**. The node is single and its root filesystem was
  86% full when this was written; every `local-path` PVC is a directory on it.
  A restore that fills the disk takes down app, Postgres, Prometheus and Loki
  together — so under `minFreeGi` the drill SKIPS and says so on Telegram. A
  skipped, visible drill beats a full node;
- a **freshness assertion** the manual checks below do not make:
  `max(ohlcv_daily.date)` must be within `maxBarAgeDays`. A backup pipeline can
  keep succeeding while archiving the same stale data, and from the outside
  that is indistinguishable from working;
- **row counts compared against the LIVE cluster**, not against hardcoded
  floors that would age into either uselessness or false alarms;
- **teardown in a `trap`**, so a drill that dies half-way still releases the
  PVC. Otherwise each failure would eat disk until the node filled.

Two Prometheus alerts watch the drill itself (`FinanceAlertRestoreDrillStale`,
`FinanceAlertRestoreDrillFailing`) — a CronJob that quietly stops running looks
exactly like one that keeps passing.

⚠️ **The drill cluster has NO `plugins` block**, so it never mounts the Barman
plugin and never archives WAL. A recovered cluster that inherits the archiving
configuration writes into the *same* object-store path as production: the drill
would corrupt the backup it exists to verify. The safety here is an ABSENT
block, which is the kind a careless edit re-adds without noticing.

To run it on demand (after any change to the backup config, as before):

```bash
kubectl --kubeconfig=$KC -n finance-alert create job --from=cronjob/finance-alert-finance-alert-drill drill-manuale-$(date +%s)
kubectl --kubeconfig=$KC -n finance-alert logs -f job/drill-manuale-…
```

Manual cleanup, should you ever run the steps by hand:

```bash
kubectl --kubeconfig=$KC delete cluster pg-restore -n finance-alert
kubectl --kubeconfig=$KC delete pvc pg-restore-1 -n finance-alert --ignore-not-found
```

### Drill log

| Date | Result | Notes |
|---|---|---|
| 2026-07-16 | pass | First end-to-end proof of the procedure. |
| 2026-09-09 | pass | 110 s to `Cluster in healthy state`. All four row counts identical to live. |
| 2026-09-13 | pass | **First AUTOMATED run** (CronJob, triggered by hand to prove it runs). 29 tables, alembic `3d8693a96ce6`, `fa_app` non-superuser, last bar 2026-09-11 (2 d), 2 479 695 / 2 479 695 rows. Teardown clean: node back to 4.4 Gi free, no leftover cluster or PVC. |

⚠️ **The identical row counts on 2026-09-13 are not luck, and not a bug.**
The backup is up to 24 h old, so a difference would be normal — but the last
bar is Friday 2026-09-11 and the drill ran on a Sunday: markets were shut, no
scan ingested anything, so the two numbers *must* match. A check whose passing
condition you cannot explain is not a check; this one is explainable.

Corollary for `maxBarAgeDays`: on the Monday 04:00 schedule the freshest bar is
normally Friday's, i.e. **3 days old**. The threshold is 5 so an extra public
holiday does not fire a false alarm — and so a series that genuinely stopped
updating still does.

**2026-09-09, what it actually established.** The July run proved the
*mechanism*. It could not prove anything about the objects sitting in the
bucket today, which is the whole reason the cadence rule above exists.

    stocks=1010  alerts=8679  ohlcv=2476821  outcomes=5031    <- restored
    stocks=1010  alerts=8679  ohlcv=2476821  outcomes=5031    <- live
    28 tables | alembic a3f71c9d2e40 | fa_app rolsuper=false

The alembic revision is the load-bearing line. `a3f71c9d2e40` is the position
FX rate book, applied the DAY BEFORE the drill, and `positions.entry_fx_rate`
/ `exit_fx_rate` were both present in the restored database. So the backup is
not merely restorable, it is CURRENT: a schema change made yesterday survives
a restore taken from the bucket today. A drill that only counts rows cannot
tell you that, because row counts would match even against a stale schema.

Note the table count is **28**, not the ~26 this runbook predicted in July. The
schema grows; treat the number as "matches live", never as a constant.

**Budget ~2 GB of transient disk, and check first.** Gotcha 4 says to check
free space without saying how much. Measured: the root volume went 82% -> 89%
during the drill and settled at 84% after deleting the cluster and its PVC.
It did not return to 82% because an unrelated image pull landed in the same
window, not because the drill leaked. On a node with under ~3 GB free, free
space first.

**The deprecation warning is now emitted on every apply** (gotcha 3):
`Native support for Barman Cloud backups and recovery is deprecated and will be
completely removed in CloudNativePG 1.31.0`. The drill still passes, but this
is the operator telling you the clock is running on the in-tree plugin.
