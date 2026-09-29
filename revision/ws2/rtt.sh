#!/bin/bash
# rtt.sh OUT_JSON — 100 ICMP echoes (0.2 s apart) between every ordered host pair,
# all sources in parallel. Records min/avg/max/mdev per pair as JSON.
set -euo pipefail
OUT=${1:?output json}
declare -A IP=([orbit-a]=10.10.1.4 [orbit-b]=10.20.1.4 [orbit-c]=10.10.1.5 [orbit-d]=10.20.1.5)
tmp=$(mktemp -d)
for src in orbit-a orbit-b orbit-c orbit-d; do
  for dst in orbit-a orbit-b orbit-c orbit-d; do
    [ "$src" = "$dst" ] && continue
    cmd="ping -c 100 -i 0.2 -q ${IP[$dst]} | tail -1"
    if [ "$src" = orbit-d ]; then (sh -c "$cmd" > "$tmp/$src-$dst") &
    else (ssh -n $src "$cmd" > "$tmp/$src-$dst") & fi
  done
done
wait
{
  echo "{"; first=1
  for f in "$tmp"/*; do
    pair=$(basename "$f"); line=$(cat "$f")   # rtt min/avg/max/mdev = a/b/c/d ms
    vals=$(echo "$line" | sed -E 's#.*= ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+) ms.*#{"min":\1,"avg":\2,"max":\3,"mdev":\4}#')
    [ $first = 1 ] || echo ","; first=0
    printf '"%s": %s' "$pair" "$vals"
  done
  echo; echo "}"
} > "$OUT"
rm -rf "$tmp"
cat "$OUT"
