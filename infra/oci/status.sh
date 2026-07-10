#!/usr/bin/env bash
# Quick status of the A1 capacity-retry bot. Run from anywhere in the repo:
#   bash infra/oci/status.sh
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$SCRIPT_DIR/a1-retry.log"

echo "── A1 bot status ──────────────────────────────────────────"
if ps -ef 2>/dev/null | grep -q "[a]1-retry.sh"; then
  pid=$(ps -ef 2>/dev/null | grep "[a]1-retry.sh" | awk '{print $2}' | head -1)
  echo "state      : 🟢 RUNNING (pid $pid)"
else
  echo "state      : 🔴 NOT running — relaunch with: bash infra/oci/a1-retry.sh"
fi

[ -f "$LOG" ] || { echo "log        : (none yet)"; exit 0; }

echo "attempts   : $(grep -c 'attempt #' "$LOG" 2>/dev/null)"
echo "capacity KO: $(grep -c 'A1 capacity unavailable' "$LOG" 2>/dev/null)"
if grep -q 'SUCCESS' "$LOG" 2>/dev/null; then
  echo "result     : 🎉 SUCCESS — VM is up:"
  grep 'SUCCESS' "$LOG" | tail -1 | sed -E 's/\x1b\[[0-9;]*m//g' | sed 's/^/             /'
elif grep -q 'non-capacity apply error' "$LOG" 2>/dev/null; then
  echo "result     : ❌ STOPPED on a non-capacity error — inspect the log tail below"
else
  echo "result     : ⏳ still waiting for A1 capacity (this is normal — can take hours)"
fi

first=$(grep -oE '^\[[0-9-]+ [0-9:]+\]' "$LOG" 2>/dev/null | head -1)
last=$(grep -oE '^\[[0-9-]+ [0-9:]+\]' "$LOG" 2>/dev/null | tail -1)
echo "running    : since ${first:-?}  ·  last event ${last:-?}  ·  now [$(date '+%F %T')]"
echo "────────────────────────────────────────────────────────────"
echo "last 4 log lines:"
tail -4 "$LOG" 2>/dev/null | sed -E 's/\x1b\[[0-9;]*m//g' | sed 's/^/  /'
echo
echo "tip: live view →  tail -f infra/oci/a1-retry.log"
