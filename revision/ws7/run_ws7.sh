#!/bin/bash
# WS7 — rerun the unchanged experiments on the single v2 deployment (Azure testbed),
# so every v2 number comes from one deployment and one configuration record.
#   exp2  privacy conformance (deterministic; once)
#   exp3  Merkle gas sweep, N in {1..200, 500, 1000}, 5 real transactions per point
#   exp4  storage (sparse + dense) and rollback latency (internal reps + CI)
#   exp8  Eq. 36 validation points and near-head recovery targets
#   exp5  exactly-once (6 sequential / 25 concurrent / 40 distinct), 5 repetitions
# Output: results/v2/raw/ws7/<exp>/rep<k>/...
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT=${WS7_OUT:-$REPO/results/v2/raw/ws7}
CTL=$REPO/scripts/orbit_v2.sh
if [ -n "${ORBIT_ENV:-}" ]; then set -a; . "$ORBIT_ENV"; set +a; fi
PY=${VENV:-/root/orbit-venv}/bin/python
mkdir -p "$OUT"; LOG=$OUT/harness.log
say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
run() {  # name rep script
  local d=$OUT/$1/rep$2; mkdir -p "$d"
  [ -f "$d/exit_code" ] && [ "$(cat "$d/exit_code")" = 0 ] && { say "skip $1 rep$2"; return; }
  "$PY" "$REPO/revision/ws7/digest_to.py" "$d/run_digest.json" >>"$LOG" 2>&1 || true
  ORBIT_RESULTS_DIR="$d" "$PY" "$REPO/experiments/$3" > "$d/stdout.txt" 2>&1
  echo $? > "$d/exit_code"; say "$1 rep$2: exit $(cat "$d/exit_code")"
}
say "WS7 start commit=$(git -c safe.directory='*' -C "$REPO" rev-parse --short HEAD)"
$CTL stop >>"$LOG" 2>&1
SERVER_PROFILE=prod $CTL services >>"$LOG" 2>&1
$CTL relay 1 1 >>"$LOG" 2>&1
run exp2 1 exp2_privacy_policy.py
run exp3 1 exp3_gas_real.py
run exp4 1 exp4_lifecycle_real.py
run exp8 1 exp8_recovery_strategy.py
for k in 1 2 3 4 5; do run exp5 $k exp5_exactly_once_real.py; done
say "WS7 done"
