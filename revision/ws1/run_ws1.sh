#!/bin/bash
# WS1 — dev vs prod application server, single host, full concurrency sweep.
#
#   REPS repetitions x {dev, prod}. The profile order alternates by repetition
#   (dev,prod | prod,dev | ...) so slow drift in the host (WSL clock rate,
#   ledger growth, thermal state) does not load onto one profile.
#   Each run: stop services, start them under the profile, start relay-1,
#   idle, clock calibration, exp1 throughput sweep (4 fixtures x 11 levels,
#   n >= 200 per level), clock calibration.
#
# Output: results/v2/raw/ws1/<profile>/rep<k>/{exp1/, clock_pre.json, clock_post.json, exit_code}
#         results/v2/raw/ws1/harness.log
#
# Usage: revision/ws1/run_ws1.sh [REPS] [extra env for exp1, e.g. EXP1_CONC=1,10]
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPS="${1:-5}"
OUT="${WS1_OUT:-$REPO/results/v2/raw/ws1}"
PY=/root/orbit-venv/bin/python
CAL_S="${WS1_CAL_S:-60}"
IDLE_S="${WS1_IDLE_S:-10}"
mkdir -p "$OUT"
LOG="$OUT/harness.log"
say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }

say "WS1 start: reps=$REPS out=$OUT commit=$(git -c safe.directory='*' -C "$REPO" rev-parse --short HEAD)"
for rep in $(seq 1 "$REPS"); do
  if [ $((rep % 2)) -eq 1 ]; then order="dev prod"; else order="prod dev"; fi
  for profile in $order; do
    d="$OUT/$profile/rep$rep"
    if [ -f "$d/exit_code" ] && [ "$(cat "$d/exit_code")" = "0" ]; then
      say "skip $profile rep$rep (already complete)"; continue; fi
    mkdir -p "$d"
    say "=== $profile rep$rep: restarting services"
    "$REPO/scripts/orbit_v2.sh" stop >>"$LOG" 2>&1
    SERVER_PROFILE=$profile "$REPO/scripts/orbit_v2.sh" services >>"$LOG" 2>&1 || { say "services failed"; echo 90 >"$d/exit_code"; continue; }
    "$REPO/scripts/orbit_v2.sh" relay 1 1 >>"$LOG" 2>&1
    sleep "$IDLE_S"
    "$PY" "$REPO/revision/ws0/clock_calibrate.py" "$CAL_S" "$d/clock_pre.json" >/dev/null 2>>"$LOG"
    say "$profile rep$rep: exp1 running"
    ORBIT_RESULTS_DIR="$d" EXP1_NONCE="ws1-$profile-r$rep-$(date +%s)" EXP1_PHASES=throughput \
      "$PY" "$REPO/experiments/exp1_latency_real.py" >"$d/exp1_stdout.txt" 2>&1
    rc=$?
    "$PY" "$REPO/revision/ws0/clock_calibrate.py" "$CAL_S" "$d/clock_post.json" >/dev/null 2>>"$LOG"
    echo "$rc" >"$d/exit_code"
    say "$profile rep$rep: exp1 exit $rc ($(grep -c 'GATE FAILED' "$d/exp1_stdout.txt") gate failures)"
  done
done
"$REPO/scripts/orbit_v2.sh" stop >>"$LOG" 2>&1
SERVER_PROFILE=dev "$REPO/scripts/orbit_v2.sh" services >>"$LOG" 2>&1
"$REPO/scripts/orbit_v2.sh" relay 1 1 >>"$LOG" 2>&1
say "WS1 done"
