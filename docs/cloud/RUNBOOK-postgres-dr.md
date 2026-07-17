# Runbook — PostgreSQL disaster recovery (M7/M9)

**The restore path below was executed and verified end-to-end on 2026-07-16**: a
throwaway cluster was bootstrapped from *nothing but the Object Storage backup*
and came up with data identical to live. This is not a theoretical procedure.

> Supersedes the Object-Storage half of `RUNBOOK-db-migration.md`, which is now
> the **SQLite-era / localhost** procedure. The cloud app runs on Postgres.

---

## What the backup actually is

| Piece | Where | Cadence |
|---|---|---|
| Base backups | `s3://finance-alert-backups/` (private OCI bucket, versioned) | `ScheduledBackup pg-daily` @ 02:00 + on demand |
| WAL segments | same bucket, gzip | continuous (`archive_command`) |
| Retention | `spec.backup.retentionPolicy: 7d` | barman prunes |

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
  method: barmanObjectStore
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
      barmanObjectStore:
        destinationPath: s3://finance-alert-backups/
        endpointURL: https://axaqdeicu0wx.compat.objectstorage.eu-milan-1.oraclecloud.com
        serverName: pg          # the ORIGIN cluster's name inside the bucket
        s3Credentials:
          accessKeyId: {name: pg-wal-s3, key: ACCESS_KEY_ID}
          secretAccessKey: {name: pg-wal-s3, key: SECRET_ACCESS_KEY}
        wal: {compression: gzip}
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
3. **In-tree barman is deprecated** (removed in CloudNativePG 1.31). At the next
   operator upgrade, migrate `spec.backup.barmanObjectStore` to the **Barman
   Cloud Plugin**.
4. **Disk.** The node root volume was ~85% full; a restore adds a second PVC.
   Check free space before starting.
5. **TLS is enforced** (`pg_hba`: `hostssl …` + `hostnossl … reject`). Clients
   must use `sslmode=require` or better; `sslmode=disable` gets
   `FATAL: pg_hba.conf rejects connection … no encryption`.

---

## Drill cadence

Re-run the drill after any change to the backup config, and periodically
otherwise. It costs a few minutes and it is the only thing that turns "backups
are configured" into "backups are known to work". Clean up afterwards:

```bash
kubectl --kubeconfig=$KC delete cluster pg-restore -n finance-alert
kubectl --kubeconfig=$KC delete pvc pg-restore-1 -n finance-alert --ignore-not-found
```
