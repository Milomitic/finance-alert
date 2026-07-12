# Runbook — migrate/restore `app.db` onto the k3s cloud pod

Executed successfully on 2026-07-13 (local → cloud, 375 MB / 96 MB gzipped).
The same steps are the **disaster-recovery restore** (M9): replace "local
snapshot" with "backup from Object Storage".

## Preconditions
- The pod's image knows the DB's alembic head (a DB *newer* than the image
  fails at boot with "Can't locate revision"). Check:
  `kubectl exec <pod> -- ls /app/backend/alembic/versions | grep <rev>`
  where `<rev>` = `SELECT version_num FROM alembic_version` on the source DB.
- Disk on the VM: snapshot + old DB coexist in the PVC during the swap.

## Steps

```bash
# 1. Consistent snapshot (safe while the local app runs — point-in-time copy)
./backend/.venv/Scripts/python.exe -c \
  "import sqlite3; sqlite3.connect('backend/data/app.db').execute(\"VACUUM INTO 'backend/data/app.db.mig.bak'\")"
gzip -6 backend/data/app.db.mig.bak          # ~375M → ~96M

# 2. Upload
scp -i ~/.ssh/oci_finance_alert backend/data/app.db.mig.bak.gz opc@<VM_IP>:/tmp/app.db.migration.gz

# 3. On the VM — stop the single writer, swap, restart
ssh -i ~/.ssh/oci_finance_alert opc@<VM_IP>
K="sudo /usr/local/bin/k3s kubectl -n finance-alert"
$K scale statefulset finance-alert-finance-alert --replicas=0
$K wait --for=delete pod/finance-alert-finance-alert-0 --timeout=180s

# PVC host path: $K get pv -o jsonpath='{..spec.hostPath.path}'
sudo sh -c '
  cd /var/lib/rancher/k3s/storage/<pvc-dir>
  mv app.db app.db.pre-migration.bak     # rollback point — NEVER plain rm
  rm -f app.db-wal app.db-shm            # stale WAL would corrupt the new DB
  gunzip -c /tmp/app.db.migration.gz > app.db
  chown 10001:10001 app.db && chmod 644 app.db
'
$K scale statefulset finance-alert-finance-alert --replicas=1
# (the pod object may take a few seconds to exist — retry the wait)
$K wait --for=condition=ready pod/finance-alert-finance-alert-0 --timeout=240s

# 4. Verify
curl -s http://<VM_IP>/api/health                      # 200 {"status":"ok"}
# row counts vs the source, admin hash sha256, wrong-password login → 401
```

## Rollback
```bash
# scale 0 → restore the .pre-migration.bak → scale 1
sudo sh -c 'cd <pvc-dir> && mv app.db app.db.failed && mv app.db.pre-migration.bak app.db'
```

## Gotchas hit live (already encoded above)
- `cd` into the PVC dir as `opc` → permission denied: the storage path is
  root-only. Run the whole swap under `sudo sh -c`.
- `kubectl wait --for=condition=ready` right after `scale 1` can race the pod's
  creation (NotFound) — poll for existence first.
- The k3s cloud scheduler **self-populates an empty DB** (index sync → 738
  stocks, OHLCV backfill, alerts). Don't assume the target is empty: inspect
  before overwriting, and keep `app.db.pre-migration.bak` until verified.
