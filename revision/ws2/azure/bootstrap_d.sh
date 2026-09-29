#!/bin/bash
# Run on the laptop (WSL root). Makes orbit-d the control host of the testbed.
set -euo pipefail
B=/root/orbit-azure/repo.bundle
say() { echo "[$(date -u +%FT%TZ)] $*"; }

say "repo -> orbit-d"
scp -q $B orbit-d:/tmp/repo.bundle
ssh orbit-d 'sudo bash -s' <<'R'
set -e
mkdir -p /opt/orbit && cd /opt/orbit
if [ ! -d Hybrid_BC_System ]; then git clone -q -b revision/v2 /tmp/repo.bundle Hybrid_BC_System; fi
cd Hybrid_BC_System && git fetch -q /tmp/repo.bundle revision/v2 && git checkout -q -B revision/v2 FETCH_HEAD
git log --oneline -1
ln -sf /opt/orbit/Hybrid_BC_System/revision/ws2/azure/azure.env /opt/orbit/azure.env
mkdir -p /opt/orbit-state
# root key for driving the other VMs over the private network
[ -f /root/.ssh/id_ed25519 ] || ssh-keygen -q -t ed25519 -N "" -C orbit-d-control -f /root/.ssh/id_ed25519
cat > /root/.ssh/config <<'C'
Host orbit-a
  HostName 10.10.1.4
Host orbit-b
  HostName 10.20.1.4
Host orbit-c
  HostName 10.10.1.5
Host orbit-*
  User azureuser
  StrictHostKeyChecking accept-new
  ConnectTimeout 10
C
chmod 600 /root/.ssh/config
R
PUB=$(ssh orbit-d 'sudo cat /root/.ssh/id_ed25519.pub')
for h in orbit-a orbit-b orbit-c; do
  ssh $h "grep -qF '$PUB' ~/.ssh/authorized_keys || echo '$PUB' >> ~/.ssh/authorized_keys"
done
ssh orbit-d 'sudo bash -c "for h in orbit-a orbit-b orbit-c; do ssh -o BatchMode=yes \$h hostname; done"'

say "truffle on orbit-d"
ssh orbit-d 'sudo bash -s' <<'R'
set -e
cd /opt/orbit/Hybrid_BC_System/blockchain/setup/ethereum
# the committed node_modules came from Windows (.cmd shims, no symlinks): replace
# it with a Linux install of the same versions the laptop ran
rm -rf node_modules
npm install --no-audit --no-fund --silent truffle@5.11.5 ganache@7.9.1 >/dev/null 2>&1
npx truffle version | head -3
git -C /opt/orbit/Hybrid_BC_System checkout -q -- . 2>/dev/null || true
R

say "ganache on orbit-c"
ssh orbit-c 'sudo bash -s' <<'R'
set -e
mkdir -p /opt/orbit-state/ganache-db /opt/orbit-state/logs
if ! curl -sf -X POST -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' http://127.0.0.1:8545 >/dev/null; then
  setsid nohup ganache --host 0.0.0.0 --port 8545 --chain.chainId 1337 --chain.networkId 1337 \
    --wallet.deterministic --database.dbPath /opt/orbit-state/ganache-db \
    > /opt/orbit-state/logs/ganache.log 2>&1 < /dev/null &
  echo $! > /opt/orbit-state/ganache.pid
  sleep 8
fi
curl -s -X POST -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' http://127.0.0.1:8545; echo
R
ssh orbit-d "curl -s -X POST -H 'Content-Type: application/json' --data '{\"jsonrpc\":\"2.0\",\"method\":\"eth_blockNumber\",\"params\":[],\"id\":1}' http://10.10.1.5:8545"; echo
say "done"
