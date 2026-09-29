#!/bin/bash
# Move the testbed from burstable B-series to fixed-performance D-series and start it.
# B-series VMs drop to a fraction of a vCPU once burst credits are spent, which
# would change performance part-way through multi-hour runs. Quota per region:
# 4 vCPU in each of DSv3 / DASv4 / DSv4 families, 6 cores total, so two 2-vCPU
# VMs per region.
set -euo pipefail
RG=orbit-rev
SIZES=${SIZES:-"Standard_D2s_v3 Standard_D2as_v4 Standard_D2s_v4"}
for vm in orbit-a orbit-c orbit-b orbit-d; do
  cur=$(az vm show -g $RG -n $vm --query hardwareProfile.vmSize -o tsv)
  if [[ " $SIZES " == *" $cur "* ]]; then echo "$vm already $cur"; continue; fi
  done_=""
  for s in $SIZES; do
    if az vm resize -g $RG -n $vm --size $s -o none 2>/tmp/resize_err; then
      echo "$vm: $cur -> $s"; done_=1; break
    fi
    echo "$vm: $s unavailable ($(grep -o -m1 'SkuNotAvailable\|QuotaExceeded\|OperationNotAllowed' /tmp/resize_err || head -c 200 /tmp/resize_err))"
  done
  [ -n "$done_" ] || { echo "FATAL: no D-series size for $vm"; exit 1; }
done
for vm in orbit-a orbit-c orbit-b orbit-d; do az vm start -g $RG -n $vm --no-wait; done
az vm wait -g $RG -n orbit-d --custom "instanceView.statuses[?code=='PowerState/running']" --timeout 600
sleep 20
az vm list -g $RG -d --query "[].{name:name, size:hardwareProfile.vmSize, state:powerState, public:publicIps}" -o table
