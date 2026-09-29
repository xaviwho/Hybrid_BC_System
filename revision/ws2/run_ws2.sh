#!/bin/bash
# WS2 on the Azure multi-VM testbed (topology_mode multi_vm), run on orbit-d as root.
#
# Configurations (name | netem one-way ms | MaxMessageCount | BatchTimeout | fixtures | levels):
#   base          real Azure paths, BT 2 s / MMC 10 (the manuscript's settings), 4 fixtures
#   d10 d25 d50   + netem one-way delay on every inter-host link (RTT + 2x), 2 fixtures
#   m5 m20        MaxMessageCount 5 / 20 at BT 2 s          (Eq. 8: transition at c = MMC)
#   t05 t1        BatchTimeout 0.5 s / 1 s at MMC 10        (Eq. 8: sub-threshold floor ~ BT)
# All runs use the prod server profile (gunicorn), one relay (account 1).
# REPS repetitions; within each, every configuration runs once, in an order
# rotated by repetition, so slow drift does not load onto one configuration.
#
# Per run: batch parameters, netem, RTT matrix (100 pings/pair), relay queue
# drained, services restarted, per-host vmstat during exp1, exp1 throughput sweep.
# Output: results/v2/raw/ws2/<config>/rep<k>/...   log: results/v2/raw/ws2/harness.log
set -u
REPO=/opt/orbit/Hybrid_BC_System
REPS=${1:-5}
OUT=${WS2_OUT:-$REPO/results/v2/raw/ws2}
ONLY=${WS2_ONLY:-}          # comma list to restrict configs (testing)
W=$REPO/revision/ws2/azure/with_env.sh
NET=$REPO/revision/ws2/net/netctl.sh
ALL4=all_public,all_sensitive,mixed,fabric_only
TWO=mixed,fabric_only
GRID=1,2,4,8,10,12,14,16,20,24,32
XGRID=1,2,4,5,6,8,10,12,16,18,20,22,24,32
CONFIGS=(
  "base|0|10|2s|$ALL4|$GRID"
  "d10|10|10|2s|$TWO|$GRID"
  "d25|25|10|2s|$TWO|$GRID"
  "d50|50|10|2s|$TWO|$GRID"
  "m5|0|5|2s|$TWO|$XGRID"
  "m20|0|20|2s|$TWO|$XGRID"
  "t05|0|10|500ms|$TWO|$XGRID"
  "t1|0|10|1s|$TWO|$XGRID"
)
mkdir -p "$OUT"; LOG=$OUT/harness.log
say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
restart_services() {
  ORBIT_ENV=/opt/orbit/azure.env $REPO/scripts/orbit_v2.sh stop >>"$LOG" 2>&1
  ORBIT_ENV=/opt/orbit/azure.env SERVER_PROFILE=prod $REPO/scripts/orbit_v2.sh services >>"$LOG" 2>&1 || return 1
  ORBIT_ENV=/opt/orbit/azure.env $REPO/scripts/orbit_v2.sh relay 1 1 >>"$LOG" 2>&1
}
wait_drained() {
  for _ in $(seq 360); do
    d=$(curl -s -m 10 http://127.0.0.1:5002/outbox_depth | python3 -c 'import json,sys; print(json.load(sys.stdin)["queue_depth"])' 2>/dev/null || echo "?")
    [ "$d" = 0 ] && return 0; sleep 5
  done; say "WARNING: relay queue not drained after 30 min (depth $d)"
}
vmstat_start() { for h in orbit-a orbit-b orbit-c; do ssh -n $h "nohup vmstat -n -t 5 > /tmp/vmstat.log 2>&1 & echo \$! > /tmp/vmstat.pid"; done
                 nohup vmstat -n -t 5 > /tmp/vmstat.log 2>&1 & echo $! > /tmp/vmstat.pid; }
vmstat_stop() {  # dir
  for h in orbit-a orbit-b orbit-c; do ssh -n $h 'kill $(cat /tmp/vmstat.pid) 2>/dev/null; cat /tmp/vmstat.log' > "$1/vmstat_$h.txt"; done
  kill "$(cat /tmp/vmstat.pid)" 2>/dev/null; cp /tmp/vmstat.log "$1/vmstat_orbit-d.txt"
}

say "WS2 start reps=$REPS commit=$(git -C $REPO rev-parse --short HEAD)"
n=${#CONFIGS[@]}
for rep in $(seq 1 "$REPS"); do
  for j in $(seq 0 $((n - 1))); do
    spec=${CONFIGS[$(( (j + rep - 1) % n ))]}
    IFS='|' read -r name ms mmc bt classes conc <<<"$spec"
    [ -n "$ONLY" ] && [[ ",$ONLY," != *",$name,"* ]] && continue
    d=$OUT/$name/rep$rep
    if [ -f "$d/exit_code" ] && [ "$(cat "$d/exit_code")" = 0 ]; then say "skip $name rep$rep"; continue; fi
    mkdir -p "$d"
    say "=== $name rep$rep (netem ${ms} ms, MMC $mmc, BT $bt)"
    bash $NET batch "$mmc" "$bt" >>"$LOG" 2>&1 || { say "batch update failed"; echo 91 > "$d/exit_code"; continue; }
    bash $REPO/revision/ws2/netem.sh "$ms" >>"$LOG" 2>&1
    bash $REPO/revision/ws2/rtt.sh "$d/rtt.json" > /dev/null 2>>"$LOG"
    wait_drained
    restart_services || { say "services failed"; echo 90 > "$d/exit_code"; continue; }
    sleep 5
    vmstat_start
    ORBIT_RESULTS_DIR="$d" EXP1_NONCE="ws2-$name-r$rep-$(date +%s)" EXP1_PHASES=throughput \
      EXP1_CLASSES="$classes" EXP1_CONC="$conc" $W python experiments/exp1_latency_real.py > "$d/exp1_stdout.txt" 2>&1
    rc=$?
    vmstat_stop "$d"
    echo $rc > "$d/exit_code"
    say "$name rep$rep: exp1 exit $rc ($(grep -c 'GATE FAILED' "$d/exp1_stdout.txt") gate failures)"
  done
done
bash $NET batch 10 2s >>"$LOG" 2>&1
bash $REPO/revision/ws2/netem.sh 0 >>"$LOG" 2>&1
say "WS2 done"
