#!/bin/bash
# netctl.sh — the multi-VM Fabric network for WS2+ (runs on orbit-d as root).
#
#   crypto     cryptogen for Org1, Org2, Orderer into $NET/organizations
#   push       give each host only its own crypto + its compose file + peercfg
#   up|down    start/stop containers on orbit-a (Org1), orbit-b (Org2), orbit-c (orderer)
#   channel    genesis block (profile ChannelUsingRaft, as on the laptop), osnadmin
#              join on the orderer, peer channel join on both peers
#   cc         package/install/approve/commit iot-data with AND(Org1,Org2)
#   batch MMC BT   channel config update: BatchSize.MaxMessageCount, BatchTimeout
#   status     containers per host + channel height + committed chaincode
#
# Differences from the laptop network (recorded in the run digest and README):
# crypto from cryptogen rather than Fabric CA; chaincode iot-data v2.1 seq 1
# (v2.0 + ListRecords) on a fresh channel.
set -euo pipefail
REPO=${REPO:-/opt/orbit/Hybrid_BC_System}
SRC=$REPO/revision/ws2/net
NET=${NET:-/opt/orbit-net}
FAB=${FAB:-/opt/fabric}
export PATH=$FAB/bin:$PATH FABRIC_CFG_PATH=$FAB/config
CH=hiot
CC_NAME=iot-data CC_VERSION=${CC_VERSION:-2.1} CC_SEQ=${CC_SEQ:-1}
CC_POLICY="AND('Org1MSP.peer','Org2MSP.peer')"
ORD=orderer.example.com:7050
ORD_CA=$NET/organizations/ordererOrganizations/example.com/tlsca/tlsca.example.com-cert.pem
ORD_ADMIN_CERT=$NET/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.crt
ORD_ADMIN_KEY=$NET/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/tls/server.key
O1=$NET/organizations/peerOrganizations/org1.example.com
O2=$NET/organizations/peerOrganizations/org2.example.com
P1=peer0.org1.example.com:7051; P1_TLS=$O1/peers/peer0.org1.example.com/tls/ca.crt
P2=peer0.org2.example.com:9051; P2_TLS=$O2/peers/peer0.org2.example.com/tls/ca.crt
say() { echo "[$(date -u +%FT%TZ)] $*"; }

as_org() {  # 1|2
  export CORE_PEER_TLS_ENABLED=true
  if [ "$1" = 1 ]; then
    export CORE_PEER_LOCALMSPID=Org1MSP CORE_PEER_ADDRESS=$P1 CORE_PEER_TLS_ROOTCERT_FILE=$P1_TLS \
           CORE_PEER_MSPCONFIGPATH=$O1/users/Admin@org1.example.com/msp
  else
    export CORE_PEER_LOCALMSPID=Org2MSP CORE_PEER_ADDRESS=$P2 CORE_PEER_TLS_ROOTCERT_FILE=$P2_TLS \
           CORE_PEER_MSPCONFIGPATH=$O2/users/Admin@org2.example.com/msp
  fi
}
ord() { echo -o $ORD --ordererTLSHostnameOverride orderer.example.com --tls --cafile $ORD_CA; }

cmd_crypto() {
  [ -d $NET/organizations ] && { say "crypto exists; refusing to regenerate"; return 0; }
  mkdir -p $NET
  for f in org1 org2 orderer; do
    cryptogen generate --config=$SRC/cryptogen/crypto-config-$f.yaml --output=$NET/organizations
  done
  say "crypto generated"
}

cmd_push() {
  cp -r $SRC/peercfg $SRC/configtx $NET/
  for spec in "orbit-a org1 peerOrganizations/org1.example.com" \
              "orbit-b org2 peerOrganizations/org2.example.com" \
              "orbit-c orderer ordererOrganizations/example.com"; do
    set -- $spec; h=$1 f=$2 org=$3
    ssh $h "sudo mkdir -p /opt/orbit-net/organizations/$(dirname $org) && sudo chown -R azureuser /opt/orbit-net"
    tar -C $NET -cf - organizations/$org peercfg | ssh $h "tar -C /opt/orbit-net -xf -"
    scp -q $SRC/compose-$f.yaml $h:/opt/orbit-net/compose.yaml
    say "pushed $f -> $h"
  done
}

cmd_up() {
  for h in orbit-c orbit-a orbit-b; do
    ssh $h "cd /opt/orbit-net && sudo docker compose -f compose.yaml up -d" 2>&1 | tail -3
  done
  sleep 10; cmd_status
}

cmd_down() {
  for h in orbit-a orbit-b orbit-c; do ssh $h "cd /opt/orbit-net && sudo docker compose -f compose.yaml down" 2>&1 | tail -2; done
}

cmd_channel() {
  mkdir -p $NET/channel-artifacts
  FABRIC_CFG_PATH=$NET/configtx configtxgen -profile ChannelUsingRaft \
    -outputBlock $NET/channel-artifacts/$CH.block -channelID $CH
  osnadmin channel join --channelID $CH --config-block $NET/channel-artifacts/$CH.block \
    -o orderer.example.com:7053 --ca-file $ORD_CA --client-cert $ORD_ADMIN_CERT --client-key $ORD_ADMIN_KEY
  sleep 3
  for o in 1 2; do as_org $o; peer channel join -b $NET/channel-artifacts/$CH.block; done
  as_org 1; peer channel getinfo -c $CH
}

cmd_cc() {
  local pkg=$NET/$CC_NAME-$CC_VERSION.tar.gz label=${CC_NAME}_$CC_VERSION
  as_org 1
  peer lifecycle chaincode package $pkg --path $REPO/blockchain/chaincode/iot-data/go \
    --lang golang --label $label
  for o in 1 2; do as_org $o; say "install on org$o (builds in the peer's ccenv)"; peer lifecycle chaincode install $pkg; done
  as_org 1
  PKG_ID=$(peer lifecycle chaincode queryinstalled --output json | jq -r ".installed_chaincodes[] | select(.label==\"$label\") | .package_id")
  say "package id $PKG_ID"
  for o in 1 2; do
    as_org $o
    peer lifecycle chaincode approveformyorg $(ord) --channelID $CH --name $CC_NAME \
      --version $CC_VERSION --package-id $PKG_ID --sequence $CC_SEQ --signature-policy "$CC_POLICY"
  done
  as_org 1
  peer lifecycle chaincode checkcommitreadiness --channelID $CH --name $CC_NAME --version $CC_VERSION \
    --sequence $CC_SEQ --signature-policy "$CC_POLICY" --output json
  peer lifecycle chaincode commit $(ord) --channelID $CH --name $CC_NAME --version $CC_VERSION \
    --sequence $CC_SEQ --signature-policy "$CC_POLICY" \
    --peerAddresses $P1 --tlsRootCertFiles $P1_TLS --peerAddresses $P2 --tlsRootCertFiles $P2_TLS
  peer lifecycle chaincode querycommitted --channelID $CH --name $CC_NAME --output json
}

cmd_batch() {  # MaxMessageCount BatchTimeout(e.g. 2s)
  local mmc=${1:?MaxMessageCount} bt=${2:?BatchTimeout e.g. 2s} w=$NET/cfgupd; rm -rf $w; mkdir -p $w
  export CORE_PEER_LOCALMSPID=OrdererMSP CORE_PEER_TLS_ENABLED=true \
         CORE_PEER_MSPCONFIGPATH=$NET/organizations/ordererOrganizations/example.com/users/Admin@example.com/msp \
         CORE_PEER_TLS_ROOTCERT_FILE=$ORD_CA CORE_PEER_ADDRESS=$ORD
  peer channel fetch config $w/config_block.pb $(ord) -c $CH
  configtxlator proto_decode --input $w/config_block.pb --type common.Block | jq .data.data[0].payload.data.config > $w/config.json
  jq ".channel_group.groups.Orderer.values.BatchSize.value.max_message_count = $mmc
      | .channel_group.groups.Orderer.values.BatchTimeout.value.timeout = \"$bt\"" $w/config.json > $w/modified.json
  if cmp -s <(jq -S . $w/config.json) <(jq -S . $w/modified.json); then say "batch already MMC=$mmc BT=$bt"; return 0; fi
  configtxlator proto_encode --input $w/config.json --type common.Config --output $w/config.pb
  configtxlator proto_encode --input $w/modified.json --type common.Config --output $w/modified.pb
  configtxlator compute_update --channel_id $CH --original $w/config.pb --updated $w/modified.pb --output $w/update.pb
  configtxlator proto_decode --input $w/update.pb --type common.ConfigUpdate | jq . > $w/update.json
  echo "{\"payload\":{\"header\":{\"channel_header\":{\"channel_id\":\"$CH\", \"type\":2}},\"data\":{\"config_update\":$(cat $w/update.json)}}}" \
    | jq . > $w/envelope.json
  configtxlator proto_encode --input $w/envelope.json --type common.Envelope --output $w/envelope.pb
  peer channel update -f $w/envelope.pb -c $CH $(ord)
  sleep 3
  peer channel fetch config $w/after.pb $(ord) -c $CH
  configtxlator proto_decode --input $w/after.pb --type common.Block \
    | jq -c '.data.data[0].payload.data.config.channel_group.groups.Orderer.values | {mmc: .BatchSize.value.max_message_count, bt: .BatchTimeout.value.timeout}'
}

cmd_status() {
  for h in orbit-a orbit-b orbit-c; do echo "== $h"; ssh $h "sudo docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'"; done
  as_org 1
  peer channel getinfo -c $CH 2>/dev/null || true
  peer lifecycle chaincode querycommitted --channelID $CH --name $CC_NAME 2>/dev/null || true
}

sub=${1:-status}; shift || true
"cmd_$sub" "$@"
