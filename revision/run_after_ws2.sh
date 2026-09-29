#!/bin/bash
# Unattended chain on orbit-d after WS2: endorsement probe, WS3, WS5, WS4, WS7.
# Every step writes under results/v2/raw/ and is resumable (completed runs are skipped).
set -u
REPO=/opt/orbit/Hybrid_BC_System
export ORBIT_ENV=/opt/orbit/azure.env
W=$REPO/revision/ws2/azure/with_env.sh
LOG=$REPO/results/v2/raw/chain.log
mkdir -p "$(dirname "$LOG")"
say() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
say "chain start commit=$(git -C $REPO rev-parse --short HEAD)"
bash $REPO/revision/ws2/net/netctl.sh batch 10 2s >>"$LOG" 2>&1
bash $REPO/revision/ws2/netem.sh 0 >>"$LOG" 2>&1

say "WS2 endorsement-stage probe"
mkdir -p $REPO/results/v2/raw/ws2_probe
[ -f $REPO/results/v2/raw/ws2_probe/stage_probe.json ] || \
  $W python revision/ws2/stage_probe.py results/v2/raw/ws2_probe/stage_probe.json >>"$LOG" 2>&1
say "probe exit $?"

say "WS3"
$W python revision/ws3/run_ws3.py --part all --reps 5 --lambdas 2,4,8,16 --T 40 --M 60 \
  > $REPO/results/v2/raw/ws3_stdout.txt 2>&1
say "WS3 exit $?"

say "WS5 crash window"
for k in 1 2 3 4 5; do
  [ -f $REPO/results/v2/raw/ws5/rep$k/result.json ] && continue
  $W python revision/ws5/crash_window.py --N 30 --rep $k >> $REPO/results/v2/raw/ws5_stdout.txt 2>&1
  say "WS5 rep$k exit $?"
done

say "WS4"
bash $REPO/revision/ws4/run_ws4.sh 5 >>"$LOG" 2>&1
say "WS4 exit $?"

say "WS7"
bash $REPO/revision/ws7/run_ws7.sh >>"$LOG" 2>&1
say "WS7 exit $?"
say "chain done"
