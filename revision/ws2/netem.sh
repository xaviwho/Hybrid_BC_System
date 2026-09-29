#!/bin/bash
# netem.sh <one_way_ms> — add a one-way delay to every testbed-to-testbed packet,
# on top of the real Azure path (Korea Central <-> Japan East).
# Runs on orbit-d as root; applies to orbit-a/b/c over SSH and to itself locally.
# 0 removes the shaping. Only packets addressed to another testbed VM are
# delayed (prio band 3 + u32 dst filters), so SSH from the admin host and
# traffic to Azure services are not.
set -euo pipefail
MS=${1:?one-way delay in ms (0 = clear)}
declare -A IP=([orbit-a]=10.10.1.4 [orbit-b]=10.20.1.4 [orbit-c]=10.10.1.5 [orbit-d]=10.20.1.5)
DEV=eth0
script_for() {  # host -> shell script to run as root on that host
  local me=$1 s="tc qdisc del dev $DEV root 2>/dev/null || true;"
  if [ "$MS" != 0 ]; then
    s+=" tc qdisc add dev $DEV root handle 1: prio bands 3;"
    s+=" tc qdisc add dev $DEV parent 1:3 handle 30: netem delay ${MS}ms;"
    for h in "${!IP[@]}"; do
      [ "$h" = "$me" ] && continue
      s+=" tc filter add dev $DEV protocol ip parent 1: prio 1 u32 match ip dst ${IP[$h]}/32 flowid 1:3;"
    done
  fi
  echo "$s"
}
for h in orbit-a orbit-b orbit-c; do ssh -n $h "sudo sh -c '$(script_for $h)'"; done
sh -c "$(script_for orbit-d)"
echo "netem one-way ${MS} ms applied on a,b,c,d"
