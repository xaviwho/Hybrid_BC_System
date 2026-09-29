#!/bin/bash
# WS4 — synchronous direct-anchor baseline vs OrBIT's async outbox (Reviewer 1.3).
#
# Arms (same route, policy, payloads, commitment, contract; prod server profile):
#   sync      ORCH_MODE=sync_anchor, no relay: ack only after the anchor is mined
#             (receipt, z = 1 on instamine Ganache — the same z the relay waits for).
#             Fixture `mixed` (HYBRID).
#   async     ORCH_MODE=async_outbox + relay-1: ack after the private commit.
#             Fixtures `mixed` and `fabric_only` (the no-anchor control), plus a
#             sequential latency phase on `mixed` for T_cmp (completion latency).
# REPS repetitions; arm order alternates by repetition. Full concurrency grid.
# Runs on the measurement host (ORBIT_ENV for the Azure testbed).
# Output: results/v2/raw/ws4/<arm>/rep<k>/...
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPS=${1:-5}
OUT=${WS4_OUT:-$REPO/results/v2/raw/ws4}
CTL=$REPO/scripts/orbit_v2.sh
if [ -n "${ORBIT_ENV:-}" ]; then set -a; . "$ORBIT_ENV"; set +a; fi
VENV=${VENV:-/root/orbit-venv}
GRID=${WS4_GRID:-1,2,4,8,10,12,14,16,20,24,32}
mkdir -p "$OUT"; LOG=$OUT/harness.log
say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
drained() { for _ in $(seq 360); do [ "$(curl -s -m 10 http://127.0.0.1:5002/outbox_depth | python3 -c 'import json,sys;print(json.load(sys.stdin)["queue_depth"])' 2>/dev/null)" = 0 ] && return 0; sleep 5; done; say "WARN: not drained"; }

run_arm() {  # arm rep
  local arm=$1 rep=$2 d=$OUT/$1/rep$2
  if [ -f "$d/exit_code" ] && [ "$(cat "$d/exit_code")" = 0 ]; then say "skip $arm rep$rep"; return; fi
  mkdir -p "$d"
  $CTL stop >>"$LOG" 2>&1
  if [ "$arm" = sync ]; then
    ORCH_MODE=sync_anchor SERVER_PROFILE=prod $CTL services >>"$LOG" 2>&1
    phases=throughput classes=mixed
  else
    ORCH_MODE=async_outbox SERVER_PROFILE=prod $CTL services >>"$LOG" 2>&1
    $CTL relay 1 1 >>"$LOG" 2>&1
    phases=latency,throughput classes=mixed,fabric_only
  fi
  sleep 5
  say "$arm rep$rep: exp1 ($phases; $classes)"
  ORBIT_RESULTS_DIR="$d" EXP1_NONCE="ws4-$arm-r$rep-$(date +%s)" EXP1_PHASES=$phases \
    EXP1_CLASSES=$classes EXP1_CONC=$GRID "$VENV/bin/python" "$REPO/experiments/exp1_latency_real.py" \
    > "$d/exp1_stdout.txt" 2>&1
  echo $? > "$d/exit_code"
  say "$arm rep$rep: exit $(cat "$d/exit_code") ($(grep -c 'GATE FAILED' "$d/exp1_stdout.txt") gate failures)"
  drained
}

say "WS4 start reps=$REPS commit=$(git -c safe.directory='*' -C "$REPO" rev-parse --short HEAD)"
for rep in $(seq 1 "$REPS"); do
  if [ $((rep % 2)) -eq 1 ]; then run_arm sync $rep; run_arm async $rep
  else run_arm async $rep; run_arm sync $rep; fi
done
$CTL stop >>"$LOG" 2>&1
SERVER_PROFILE=prod $CTL services >>"$LOG" 2>&1; $CTL relay 1 1 >>"$LOG" 2>&1
say "WS4 done"
