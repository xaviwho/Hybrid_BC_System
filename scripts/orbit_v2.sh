#!/bin/bash
# orbit_v2.sh - bring the v2 measurement stack up and down (revision WS0.5).
#
# Replaces the hand-typed commands in STACK_BRINGUP.md for v2 runs. All state
# lives on ext4 under $STATE; nothing is written to /mnt/*.
#
#   orbit_v2.sh ganache         start Ganache with a persistent database
#   orbit_v2.sh deploy          compile + migrate IoTDataRegistry (ONCE per v2)
#   orbit_v2.sh chaincode       upgrade iot-data to the v2 chaincode (ONCE per v2)
#   orbit_v2.sh services        start policy service + orchestrator (dev server)
#   orbit_v2.sh relay N [IDX]   start relay process N using eth.accounts[IDX]
#   orbit_v2.sh stop            stop orchestrator, policy service, relays
#   orbit_v2.sh status          health of every component
#
# Environment overrides: STATE, ORCH_PORT, POLICY_PORT, FABRIC_READBACK.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Host-specific overrides (e.g. /opt/orbit/azure.env on orbit-d): STATE, VENV,
# FAB, FABRIC_TEST_NETWORK, FABRIC_ORDERER, FABRIC_PEER{1,2}_ADDR, GANACHE_URL,
# GANACHE_HOST. Defaults are the laptop (WSL) layout.
if [ -n "${ORBIT_ENV:-}" ]; then . "$ORBIT_ENV"; fi
STATE="${STATE:-/root/orbit-state/v2}"
LOGS="$STATE/logs"
VENV="${VENV:-/root/orbit-venv}"
PY=$VENV/bin/python
ETH="$REPO/blockchain/setup/ethereum"
FAB="${FAB:-/root/fabric-clean}"
ORCH_PORT="${ORCH_PORT:-5002}"
POLICY_PORT="${POLICY_PORT:-5011}"
mkdir -p "$STATE" "$LOGS"

case "$(stat -f -c %T "$STATE")" in
  ext2/ext3|ext4|xfs|btrfs|tmpfs) ;;
  *) echo "FATAL: $STATE is on $(stat -f -c %T "$STATE"), need a native Linux fs" >&2; exit 1;;
esac

export GANACHE_URL="${GANACHE_URL:-http://127.0.0.1:8545}"
export OUTBOX_DB="$STATE/outbox.db"
export FABRIC_BIN=$FAB/bin FABRIC_CFG_PATH=$FAB/config
export FABRIC_TEST_NETWORK="${FABRIC_TEST_NETWORK:-$FAB/test-network}"
export FABRIC_CHANNEL=hiot FABRIC_CC_NAME=iot-data
export PRIVACY_FILTER_URL="http://127.0.0.1:$POLICY_PORT/filter_data"
export FABRIC_READBACK="${FABRIC_READBACK:-sync}"

wait_http() {  # url, seconds
  for _ in $(seq "$2"); do curl -sf "$1" >/dev/null && return 0; sleep 1; done
  echo "FATAL: $1 did not come up" >&2; return 1
}

start_bg() {  # name, logfile, command...
  local name=$1 log=$2; shift 2
  # setsid: own session, so the wsl.exe session ending does not SIGHUP it
  # (Ganache treats SIGHUP as shutdown even under nohup).
  setsid nohup "$@" >"$log" 2>&1 </dev/null &
  echo $! >"$STATE/$name.pid"
  echo "$name pid $(cat "$STATE/$name.pid") log $log"
}

stop_pid() {
  local f="$STATE/$1.pid"
  [ -f "$f" ] || return 0
  local p; p=$(cat "$f")
  if kill -0 "$p" 2>/dev/null; then kill "$p"; for _ in $(seq 20); do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done; fi
  rm -f "$f"; echo "stopped $1 ($p)"
}

cmd_ganache() {
  if curl -sf -X POST -H 'Content-Type: application/json' \
       --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' $GANACHE_URL >/dev/null; then
    echo "ganache already listening on 8545"; return 0; fi
  cd "$ETH"
  # Persistent chain: a restart keeps the v2 contract, so every v2 experiment
  # stays on ONE deployment. Same wallet/ids as v1 (STACK_BRINGUP §2).
  start_bg ganache "$LOGS/ganache.log" npx ganache --host 127.0.0.1 --port 8545 \
    --chain.chainId 1337 --chain.networkId 1337 --wallet.deterministic \
    --database.dbPath "$STATE/ganache-db"
  for _ in $(seq 60); do
    curl -sf -X POST -H 'Content-Type: application/json' \
      --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' $GANACHE_URL >/dev/null && { echo "ganache up"; return 0; }
    sleep 1; done
  echo "FATAL: ganache did not start; see $LOGS/ganache.log" >&2; exit 1
}

cmd_deploy() {
  if [ -f "$STATE/DEPLOYED" ]; then
    echo "FATAL: v2 contract already deployed ($(cat "$STATE/DEPLOYED")). One deployment per result set." >&2
    exit 1; fi
  cd "$ETH"
  npx truffle migrate --network development --reset 2>&1 | tee "$LOGS/truffle_migrate.log" | tail -25
  cd "$REPO"
  "$PY" - <<'PY' | tee "$STATE/DEPLOYED"
import os, sys; sys.path.insert(0, 'orchestrator')
import contract_registry as cr
from web3 import Web3
w3 = Web3(Web3.HTTPProvider(os.environ['GANACHE_URL']))
r = cr.resolve('blockchain/setup/ethereum/build/contracts/IoTDataRegistry.json', w3=w3, require_code=True)
c = w3.eth.contract(address=r['address'], abi=r['abi'])
code = w3.eth.get_code(r['address'])
relays = [i for i, a in enumerate(w3.eth.accounts[:4]) if c.functions.isRelay(a).call()]
print(f"address={r['address']} network_id={r['network_id']} code_bytes={len(code)} "
      f"code_keccak=0x{Web3.keccak(code).hex().removeprefix('0x')} relays={relays} "
      f"block={w3.eth.block_number}")
PY
}

cmd_chaincode() {
  cd $FAB/test-network
  export PATH=$FAB/bin:$PATH IMAGE_TAG=2.5.0 CA_IMAGE_TAG=1.5.5
  ./network.sh deployCC -c hiot -ccn iot-data \
    -ccp "$REPO/blockchain/chaincode/iot-data/go" -ccl go \
    -ccv 2.0 -ccs 2 -ccep "AND('Org1MSP.peer','Org2MSP.peer')" 2>&1 \
    | tee "$LOGS/deployCC.log" | tail -30
}

cmd_services() {
  # SERVER_PROFILE=dev (Werkzeug, as v1) | prod (gunicorn); see config/orbit_v2_server.env
  local profile="${SERVER_PROFILE:-dev}"
  # shellcheck source=/dev/null
  . "$REPO/config/orbit_v2_server.env"
  local gun="$VENV/bin/gunicorn"
  local gopts=(-k gthread --timeout "$GUNICORN_TIMEOUT" --keep-alive "$GUNICORN_KEEPALIVE")
  cd "$REPO"
  if ! curl -sf "http://127.0.0.1:$POLICY_PORT/health" >/dev/null; then
    cd "$REPO/ml"
    case "$profile" in
      dev)  PORT=$POLICY_PORT PYTHONPATH="$REPO/ml" ORBIT_SERVER=werkzeug ORBIT_SERVER_PROFILE=dev \
              start_bg policy "$LOGS/policy.log" "$PY" "$REPO/ml/privacy_filter/policy_service.py";;
      prod) PYTHONPATH="$REPO/ml" ORBIT_SERVER=gunicorn ORBIT_SERVER_PROFILE=prod \
              ORBIT_SERVER_WORKERS=$POLICY_PROD_WORKERS ORBIT_SERVER_THREADS=$POLICY_PROD_THREADS \
              start_bg policy "$LOGS/policy.log" "$gun" "${gopts[@]}" \
              -w "$POLICY_PROD_WORKERS" --threads "$POLICY_PROD_THREADS" \
              -b "127.0.0.1:$POLICY_PORT" privacy_filter.policy_service:app;;
      *) echo "FATAL: SERVER_PROFILE must be dev|prod" >&2; exit 1;;
    esac
    wait_http "http://127.0.0.1:$POLICY_PORT/health" 30
  fi
  cd "$REPO/orchestrator"
  case "$profile" in
    dev)  RELAY_MODE="${RELAY_MODE:-external}" ORBIT_SERVER=werkzeug ORBIT_SERVER_PROFILE=dev \
            start_bg orchestrator "$LOGS/orchestrator.log" "$PY" orchestrator.py;;
    prod) RELAY_MODE="${RELAY_MODE:-external}" ORBIT_SERVER=gunicorn ORBIT_SERVER_PROFILE=prod \
            ORBIT_SERVER_WORKERS=$ORCH_PROD_WORKERS ORBIT_SERVER_THREADS=$ORCH_PROD_THREADS \
            start_bg orchestrator "$LOGS/orchestrator.log" "$gun" "${gopts[@]}" \
            -w "$ORCH_PROD_WORKERS" --threads "$ORCH_PROD_THREADS" \
            -b "0.0.0.0:$ORCH_PORT" orchestrator:app;;
  esac
  wait_http "http://127.0.0.1:$ORCH_PORT/health" 60
  curl -s "http://127.0.0.1:$ORCH_PORT/health"; echo
}

cmd_relay() {
  local n=${1:?relay number} idx=${2:-$1}
  cd "$REPO/orchestrator"
  RELAY_ID="relay-$n" RELAY_ACCOUNT_INDEX="$idx" \
    start_bg "relay-$n" "$LOGS/relay-$n.log" "$PY" relay_worker.py
  sleep 3; tail -3 "$LOGS/relay-$n.log"
}

cmd_stop() {
  for f in "$STATE"/relay-*.pid; do [ -e "$f" ] && stop_pid "$(basename "$f" .pid)"; done
  stop_pid orchestrator; stop_pid policy
}

cmd_status() {
  echo "--- ganache"; curl -s -X POST -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' $GANACHE_URL || echo down; echo
  echo "--- policy";  curl -s "http://127.0.0.1:$POLICY_PORT/health" || echo down; echo
  echo "--- orchestrator"; curl -s "http://127.0.0.1:$ORCH_PORT/health" || echo down; echo
  echo "--- outbox"; curl -s "http://127.0.0.1:$ORCH_PORT/outbox_stats" || echo down; echo
  echo "--- deployment"; cat "$STATE/DEPLOYED" 2>/dev/null || echo "not deployed"
}

sub=${1:-status}; shift || true
case "$sub" in
  ganache|deploy|chaincode|services|relay|stop|status) "cmd_$sub" "$@";;
  *) echo "usage: $0 {ganache|deploy|chaincode|services|relay N [IDX]|stop|status}" >&2; exit 2;;
esac
