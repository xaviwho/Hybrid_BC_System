#!/bin/bash
# Create the WS2 multi-VM testbed on Azure (Azure for Students subscription).
#
#   orbit-a  Org1 peer + CouchDB            koreacentral  10.10.1.4
#   orbit-c  orderer + Ethereum node        koreacentral  10.10.1.5
#   orbit-b  Org2 peer + CouchDB            japaneast     10.20.1.4
#   orbit-d  orchestrator, policy, relays   japaneast     10.20.1.5
#
# One VNet per region, joined by global VNet peering, so the VMs reach each
# other on private addresses. The NSGs allow SSH only from ADMIN_CIDR (this
# machine) and all traffic between the two VNets; nothing else inbound.
# Idempotent enough to re-run: az create commands on existing objects update them.
set -euo pipefail
RG=orbit-rev
KEY=/root/.ssh/orbit_azure.pub
# Tried in order per VM. Standard_B2s (the first choice) had no capacity in
# koreacentral on 2026-09-29 (SkuNotAvailable); B2ls_v2 is the same 2 vCPU /
# 4 GB class, Intel; B2als_v2 is its AMD twin. Quota: Bsv2/Basv2 families 10 vCPU.
SIZES=${SIZES:-"Standard_B2ls_v2 Standard_B2als_v2"}
IMAGE=Ubuntu2204
DISK_GB=64
TAGS="project=orbit-revision"
ADMIN_CIDR="${ADMIN_CIDR:?set ADMIN_CIDR to the public IP of this machine, as a /32}"
LOG=/root/orbit-azure/create_$(date -u +%Y%m%dT%H%M%SZ).log
mkdir -p /root/orbit-azure
exec > >(tee -a "$LOG") 2>&1

say() { echo "[$(date -u +%FT%TZ)] $*"; }

say "resource group"
az group create -n $RG -l koreacentral --tags $TAGS -o none

for spec in "kr koreacentral 10.10" "jp japaneast 10.20"; do
  set -- $spec; tag=$1 loc=$2 pfx=$3
  say "vnet + nsg $tag ($loc)"
  az network vnet create -g $RG -n orbit-vnet-$tag -l $loc --address-prefixes $pfx.0.0/16 \
     --subnet-name default --subnet-prefixes $pfx.1.0/24 --tags $TAGS -o none
  az network nsg create -g $RG -n orbit-nsg-$tag -l $loc --tags $TAGS -o none
  az network nsg rule create -g $RG --nsg-name orbit-nsg-$tag -n ssh-admin --priority 100 \
     --direction Inbound --access Allow --protocol Tcp --destination-port-ranges 22 \
     --source-address-prefixes "$ADMIN_CIDR" -o none
  # VirtualNetwork service tag covers the local VNet AND peered VNets.
  az network nsg rule create -g $RG --nsg-name orbit-nsg-$tag -n intra-testbed --priority 110 \
     --direction Inbound --access Allow --protocol '*' --destination-port-ranges '*' \
     --source-address-prefixes VirtualNetwork -o none
  az network vnet subnet update -g $RG --vnet-name orbit-vnet-$tag -n default \
     --network-security-group orbit-nsg-$tag -o none
done

say "global peering kr <-> jp"
KR_ID=$(az network vnet show -g $RG -n orbit-vnet-kr --query id -o tsv)
JP_ID=$(az network vnet show -g $RG -n orbit-vnet-jp --query id -o tsv)
az network vnet peering show -g $RG -n kr-to-jp --vnet-name orbit-vnet-kr -o none 2>/dev/null ||
  az network vnet peering create -g $RG -n kr-to-jp --vnet-name orbit-vnet-kr --remote-vnet "$JP_ID" \
     --allow-vnet-access -o none
az network vnet peering show -g $RG -n jp-to-kr --vnet-name orbit-vnet-jp -o none 2>/dev/null ||
  az network vnet peering create -g $RG -n jp-to-kr --vnet-name orbit-vnet-jp --remote-vnet "$KR_ID" \
     --allow-vnet-access -o none

for spec in "orbit-a kr koreacentral 10.10.1.4" "orbit-c kr koreacentral 10.10.1.5" \
            "orbit-b jp japaneast 10.20.1.4" "orbit-d jp japaneast 10.20.1.5"; do
  set -- $spec; name=$1 tag=$2 loc=$3 ip=$4
  if az vm show -g $RG -n $name -o none 2>/dev/null; then say "vm $name exists"; continue; fi
  made=""
  for size in $SIZES; do
    say "vm $name ($loc, $ip, $size)"
    if az vm create -g $RG -n $name -l $loc --image $IMAGE --size $size \
         --admin-username azureuser --ssh-key-values "$KEY" \
         --vnet-name orbit-vnet-$tag --subnet default --private-ip-address $ip \
         --nsg "" --public-ip-sku Standard --public-ip-address $name-ip \
         --os-disk-size-gb $DISK_GB --storage-sku StandardSSD_LRS \
         --tags $TAGS role=$name -o none; then
      made=$size; break
    fi
    say "vm $name: $size failed, trying next size"
  done
  [ -n "$made" ] || { say "FATAL: no size in [$SIZES] could be created for $name"; exit 1; }
done

say "inventory"
az vm list -g $RG -d --query "[].{name:name, loc:location, size:hardwareProfile.vmSize, private:privateIps, public:publicIps, state:powerState}" -o table
say "done; log $LOG"
