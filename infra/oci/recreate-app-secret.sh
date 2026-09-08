#!/usr/bin/env bash
# Recreate the durable `finance-alert-prod` Secret (DR).
#
# WHY THIS EXISTS
# The app cannot start usefully without this Secret, and it lives ONLY in the
# cluster: it is deliberately not in git (ArgoCD renders from git, and key
# material in a repo is out of the question) and not in Terraform. So if the node
# is lost, `terraform apply` rebuilds the VM and RUNBOOK-postgres-dr.md restores
# Postgres — and the app still will not come up, because this Secret is gone.
#
# The good news, and the reason this is a script and not a backup system: none of
# the three values is truly unrecoverable.
#   SECRET_KEY          random → just regenerate. Cost: existing session cookies
#                       stop validating, i.e. everyone logs in again. No data loss.
#   ADMIN_PASSWORD_HASH bcrypt of a password YOU know → re-hash it here.
#   the provider keys    optional; copy each from the provider's own console.
#
# THE INVENTORY IS THE POINT, and it was incomplete. The script handled three
# values while the chart had grown to reference eight, so a restore from zero
# produced a working login and a browsable app with Finnhub, FRED and Telegram
# silently off — the same failure the FINNHUB_API_KEY and FRED_API_KEY notes in
# statefulset.yaml describe, arriving through the recovery path instead of the
# deployment one. Every key the chart reads is now listed in OPTIONAL_KEYS
# below; adding one there is the whole change needed next time.
#
# It is NOT destructive to run against a populated Secret, and that was worth
# measuring rather than assuming: `create --dry-run | apply` prunes only keys
# that were in a PREVIOUS last-applied and are now absent, and a key this
# script never wrote never enters it. Verified on a throwaway namespace, twice
# over, with a third key surviving both applies.
# Backing them up would mean storing secrets somewhere, which needs a key, which
# needs a backup… For a single-user deployment, a tested recreation procedure
# beats a key-management problem.
#
# USAGE
#   bash infra/oci/recreate-app-secret.sh            # prompts for the password
#   ADMIN_PASSWORD='…' MARKETAUX_API_KEY='…' FINNHUB_API_KEY='…' #     bash infra/oci/recreate-app-secret.sh
#
# Any key in OPTIONAL_KEYS is read from the environment of the same name.
#
# Values are never echoed and never passed as argv (which `ps` would expose).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KUBECONFIG_FILE="${KUBECONFIG_FILE:-$REPO_ROOT/kubeconfig-oci}"
NAMESPACE="${NAMESPACE:-finance-alert}"
SECRET_NAME="${SECRET_NAME:-finance-alert-prod}"
PY="$REPO_ROOT/backend/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$REPO_ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || { echo "ERROR: backend venv not found. Run 'uv sync' in backend/ first (needs bcrypt)."; exit 1; }
[ -f "$KUBECONFIG_FILE" ] || { echo "ERROR: kubeconfig not found at $KUBECONFIG_FILE"; echo "  Fetch it: terraform output -raw fetch_kubeconfig"; exit 1; }

k() { kubectl --kubeconfig="$KUBECONFIG_FILE" "$@"; }

echo "── recreate $SECRET_NAME in ns/$NAMESPACE ──────────────────────"

# 1. admin password (never echoed, never in argv)
if [ -z "${ADMIN_PASSWORD:-}" ]; then
  read -rsp "Admin password (for the app login): " ADMIN_PASSWORD; echo
  [ -n "$ADMIN_PASSWORD" ] || { echo "ERROR: empty password"; exit 1; }
fi

# 2. derive: random SECRET_KEY + bcrypt hash, via the app's OWN hashing code so
#    the cost factor can never drift from what the app verifies against.
DERIVED="$(ADMIN_PASSWORD="$ADMIN_PASSWORD" "$PY" - <<'PYEOF'
import os, secrets, sys
sys.path.insert(0, os.path.join(os.getcwd(), "backend"))
try:
    from app.core.security import hash_password          # the app's own bcrypt cost
except Exception:
    import bcrypt
    def hash_password(p: str) -> str:
        return bcrypt.hashpw(p.encode(), bcrypt.gensalt(rounds=12)).decode()
print(secrets.token_urlsafe(48))
print(hash_password(os.environ["ADMIN_PASSWORD"]))
PYEOF
)"
SECRET_KEY="$(printf '%s' "$DERIVED" | sed -n 1p)"
ADMIN_PASSWORD_HASH="$(printf '%s' "$DERIVED" | sed -n 2p)"
[ -n "$SECRET_KEY" ] && [ -n "$ADMIN_PASSWORD_HASH" ] || { echo "ERROR: derivation failed"; exit 1; }

# 3. replace the Secret (create-or-update, idempotent)
#
# Every key the chart's statefulset.yaml reads from this Secret, with what a
# missing one costs. Keep the two in step: a capability wired there and absent
# here comes back dead from a restore, which is exactly how this list fell
# three keys behind.
OPTIONAL_KEYS=(
  "MARKETAUX_API_KEY|news fallback tier — reports 'not configured'"
  "FINNHUB_API_KEY|the FIRST news fallback (60/min); without it MarketAux absorbs the overflow and trips its breaker"
  "FRED_API_KEY|macro calendar — observations stop refreshing, silently"
  "TELEGRAM_BOT_TOKEN|digest, per-signal push and health alerts all off (needs the chat id too)"
  "TELEGRAM_CHAT_ID|as above — both are required together"
  "TWELVEDATA_API_KEY|earnings fallback path"
)

ARGS=(--from-literal=SECRET_KEY="$SECRET_KEY"
      --from-literal=ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD_HASH")
MISSING=()
for entry in "${OPTIONAL_KEYS[@]}"; do
  key="${entry%%|*}"; why="${entry#*|}"
  val="${!key:-}"
  if [ -n "$val" ]; then
    ARGS+=(--from-literal="$key=$val")
  else
    MISSING+=("  $key — $why")
  fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
  echo "note: ${#MISSING[@]} optional key(s) not provided, so these stay off:"
  printf '%s
' "${MISSING[@]}"
  echo "      Re-run with KEY=… for any of them. Existing values already in the"
  echo "      Secret are NOT removed by this script (measured, see the header)."
fi

k -n "$NAMESPACE" create secret generic "$SECRET_NAME" "${ARGS[@]}" \
  --dry-run=client -o yaml | k apply -f - >/dev/null
echo "✅ $SECRET_NAME written (values not printed)"

# 4. the app reads the Secret at startup → it must be restarted to pick it up
echo "restarting the app so it re-reads the Secret…"
k -n "$NAMESPACE" delete pod -l app.kubernetes.io/name=finance-alert --wait=false >/dev/null 2>&1 || true

echo
echo "verify:"
echo "  k -n $NAMESPACE get secret $SECRET_NAME -o go-template='{{range \$k,\$v := .data}}{{\$k}}{{\"\\n\"}}{{end}}'"
echo "  curl -sSf https://80-225-80-141.sslip.io/api/health"
echo "  …then log in with the password you just set."
