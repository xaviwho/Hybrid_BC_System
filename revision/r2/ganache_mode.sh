#!/bin/bash
# Restart Ganache on orbit-c on the SAME database (same genesis, registry, nonces)
# with a fixed block interval: ganache_mode.sh <B>   (B=0 -> instamine, as deployed).
# Run on orbit-c as root.
set -e
B=${1:?block time in s (0 = instamine)}
DB=/opt/orbit-state/ganache-db
LOG=/opt/orbit-state/logs/ganache.log
rpc() { curl -sf -m 3 -X POST -H 'Content-Type: application/json' \
  --data "{\"jsonrpc\":\"2.0\",\"method\":\"$1\",\"params\":[],\"id\":1}" http://127.0.0.1:8545; }

pids=$(pgrep -f "[g]anache --host" || true)
if [ -n "$pids" ]; then
  kill $pids
  for i in $(seq 1 60); do pgrep -f "[g]anache --host" >/dev/null || break; sleep 0.5; done
fi
extra=""
[ "$B" != "0" ] && extra="--miner.blockTime $B"
setsid nohup ganache --host 0.0.0.0 --port 8545 --chain.chainId 1337 --chain.networkId 1337 \
  --wallet.deterministic --database.dbPath $DB $extra >> $LOG 2>&1 < /dev/null &
for i in $(seq 1 60); do rpc eth_chainId >/dev/null && break; sleep 0.5; done
echo "ganache blockTime=$B $(rpc eth_blockNumber)"
