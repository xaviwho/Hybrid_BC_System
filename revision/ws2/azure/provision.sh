#!/bin/bash
# Provision one testbed VM. Run as root on the VM:  ROLE=a|b|c|d bash provision.sh
# Versions are pinned to the laptop v2 stack (revision/ws2/azure/README.md).
set -euo pipefail
ROLE=${ROLE:?ROLE=a|b|c|d}
FABRIC_VERSION=2.5.0
CA_VERSION=1.5.5
CCENV_TAG=2.5.12        # what the laptop peers actually built chaincode with
COUCHDB_TAG=3.4.2
GANACHE_VERSION=7.9.1
export DEBIAN_FRONTEND=noninteractive

log() { echo "[$(date -u +%FT%TZ)] [$ROLE] $*"; }

log "hosts"
sed -i '/# orbit-testbed/d' /etc/hosts
cat >> /etc/hosts <<'H'
10.10.1.4 peer0.org1.example.com orbit-a # orbit-testbed
10.20.1.4 peer0.org2.example.com orbit-b # orbit-testbed
10.10.1.5 orderer.example.com orbit-c ganache.orbit # orbit-testbed
10.20.1.5 orbit-d orchestrator.orbit # orbit-testbed
H

log "packages"
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 jq curl git iproute2 chrony python3-venv python3-pip >/dev/null
usermod -aG docker azureuser
systemctl enable --now docker >/dev/null

log "fabric binaries $FABRIC_VERSION"
mkdir -p /opt/fabric && cd /opt/fabric
if [ ! -x bin/peer ]; then
  curl -sSL "https://github.com/hyperledger/fabric/releases/download/v${FABRIC_VERSION}/hyperledger-fabric-linux-amd64-${FABRIC_VERSION}.tar.gz" | tar xz
fi
bin/peer version | head -2

log "images"
case $ROLE in
  a|b) for i in hyperledger/fabric-peer:$FABRIC_VERSION hyperledger/fabric-ccenv:$CCENV_TAG \
                hyperledger/fabric-baseos:$CCENV_TAG couchdb:$COUCHDB_TAG; do docker pull -q $i; done ;;
  c)   docker pull -q hyperledger/fabric-orderer:$FABRIC_VERSION ;;
  d)   docker pull -q hyperledger/fabric-tools:$FABRIC_VERSION ;;
esac

if [ "$ROLE" = c ] || [ "$ROLE" = d ]; then
  log "node 20"
  if ! command -v node >/dev/null || [[ "$(node --version)" != v20* ]]; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
    apt-get install -y -qq nodejs >/dev/null
  fi
  node --version
fi
if [ "$ROLE" = c ]; then
  log "ganache $GANACHE_VERSION"
  npm install -g --silent ganache@$GANACHE_VERSION
  ganache --version
fi
if [ "$ROLE" = d ]; then
  log "python venv"
  python3 -m venv /opt/orbit-venv
  /opt/orbit-venv/bin/pip install -q --upgrade pip
  /opt/orbit-venv/bin/pip install -q -r /tmp/orbit-venv-freeze.txt
  /opt/orbit-venv/bin/python -c "import web3, flask, gunicorn; print('web3', web3.__version__)"
fi
log "clock: $(chronyc tracking | grep -E 'System time' | sed 's/ \+/ /g')"
log "done"
