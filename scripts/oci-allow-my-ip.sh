#!/usr/bin/env bash
# Point the OCI NSG allowlist at wherever this machine is right now.
#
# WHY THIS EXISTS
# The NSG allowlists a single source IP on :22/:443/:6443 (see
# docs/ARCHITECTURE.md). The ISP hands out a dynamic address, so every time it
# rotates the app AND the kube-api go dark — and the symptom is indistinguishable
# from the cluster being down. It has already cost two debugging sessions.
#
# This finds the ingress rules pointing at the OLD address and repoints them at
# the current one, so the recovery is one command instead of a console trip.
#
# SAFETY
# - Only touches rules whose source is a /32 (a single pinned host). Anything
#   broader — 0.0.0.0/0 for the ACME challenge on :80, service CIDRs — is left
#   exactly as it is. Widening access is never this script's job.
# - Prints the diff and asks before writing. Locking yourself out of your own
#   cluster is the one mistake here that is genuinely annoying to undo.
# - Read-only until you confirm.
#
# SETUP (once)
#   pip install oci-cli
#   ~/.oci/config  ->  see the template printed by --help-config
set -euo pipefail

NSG_ID="${OCI_NSG_ID:-}"

usage() {
  cat <<'EOF'
usage: oci-allow-my-ip.sh [--dry-run]

  Requires OCI_NSG_ID (the Network Security Group OCID), either exported or
  in a .env next to this script.

  --dry-run     show what would change, write nothing
  --help-config print the ~/.oci/config template
EOF
}

help_config() {
  cat <<'EOF'
~/.oci/config — fill the three values from the OCI console:

[DEFAULT]
user=ocid1.user.oc1..<Profile -> User -> OCID>
tenancy=ocid1.tenancy.oc1..<Profile -> Tenancy -> OCID>
region=<e.g. eu-milan-1, shown in the console header>
key_file=~/.oci/oci_api_key.pem
fingerprint=8a:88:64:1f:74:fb:20:57:b7:d6:60:02:fb:72:da:73

The fingerprint above was computed from the key already on this machine, so it
should match what the console shows under Profile -> API Keys. If it does not,
the console key and the local key are different and the config will fail to
authenticate.
EOF
}

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --help-config) help_config; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; usage; exit 2 ;;
  esac
done

command -v oci >/dev/null 2>&1 || { echo "oci CLI not found — pip install oci-cli" >&2; exit 1; }
[ -f "$HOME/.oci/config" ] || { echo "~/.oci/config missing — run with --help-config" >&2; exit 1; }

# shellcheck disable=SC1091
[ -f "$(dirname "$0")/.env" ] && . "$(dirname "$0")/.env"
[ -n "$NSG_ID" ] || { echo "OCI_NSG_ID not set (export it, or put it in scripts/.env)" >&2; exit 1; }

MY_IP="$(curl -sS -m 10 https://api.ipify.org)"
[[ "$MY_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "could not determine this machine's public IP" >&2; exit 1; }
echo "this machine is currently: $MY_IP"

RULES="$(oci network nsg rules list --nsg-id "$NSG_ID" --direction INGRESS --all)"

# Single-host rules only. A /32 is a pinned machine — that is the thing that
# goes stale. Broader sources are deliberate and must not be rewritten.
STALE="$(echo "$RULES" | python -c "
import json,sys,ipaddress
rules = json.load(sys.stdin)['data']
me = '$MY_IP'
out = []
for r in rules:
    src = r.get('source') or ''
    if not src.endswith('/32'):
        continue
    if src == me + '/32':
        continue
    out.append({'id': r['id'], 'source': src, 'protocol': r.get('protocol')})
print(json.dumps(out))
")"

COUNT="$(echo "$STALE" | python -c "import json,sys; print(len(json.load(sys.stdin)))")"
if [ "$COUNT" -eq 0 ]; then
  echo "nothing to do: every /32 ingress rule already points at $MY_IP"
  exit 0
fi

echo
echo "the following pinned-host rules point somewhere else:"
echo "$STALE" | python -c "
import json,sys
for r in json.load(sys.stdin):
    print(f\"  {r['source']:>20}  ->  $MY_IP/32   (protocol {r['protocol']}, id {r['id'][:16]}...)\")
"

if [ "$DRY_RUN" -eq 1 ]; then
  echo; echo "--dry-run: nothing written"
  exit 0
fi

echo
read -r -p "repoint these $COUNT rule(s) at $MY_IP/32? [y/N] " reply
[ "$reply" = "y" ] || [ "$reply" = "Y" ] || { echo "aborted, nothing changed"; exit 0; }

echo "$STALE" | python -c "
import json,sys
print('\n'.join(r['id'] for r in json.load(sys.stdin)))
" | while read -r rule_id; do
  [ -n "$rule_id" ] || continue
  oci network nsg rules update \
    --nsg-id "$NSG_ID" \
    --security-rules "[{\"id\":\"$rule_id\",\"source\":\"$MY_IP/32\"}]" \
    >/dev/null
  echo "  updated $rule_id"
done

echo
echo "done. verify with:"
echo "  curl -sS -m 10 -o /dev/null -w '%{http_code}\\n' https://80-225-80-141.sslip.io/api/health"
