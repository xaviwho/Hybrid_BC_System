#!/bin/bash
# Round-2 measurements on orbit-d (as root): orderer crash x5, then inclusion
# congestion at B = 2, 6, 12 s (k = 1..3, 5 reps), then Ganache back to instamine.
cd /opt/orbit/Hybrid_BC_System
W=revision/ws2/azure/with_env.sh
OUT=results/v2/raw
for r in 1 2 3 4 5; do
  [ -f $OUT/r2_orderer/rep$r/result.json ] && continue
  bash $W python revision/r2/orderer_outage.py --rep $r --pre 60 --outage 60 --post 120 | tail -1
done
for B in 2 6 12; do
  ssh -n orbit-c "sudo bash /tmp/ganache_mode.sh $B"
  bash $W python revision/r2/congestion.py --block-time $B --k 1,2,3 --reps 5
done
ssh -n orbit-c "sudo bash /tmp/ganache_mode.sh 0"
echo R2_DONE
