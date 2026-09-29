#!/bin/bash
# Replace Ubuntu docker.io 29.1.3 with Docker Engine 28.3.2 (the laptop's engine).
# docker.io 29.1.3 panics (dockerd goroutine crash) on the legacy image-build
# request Fabric 2.5.0 peers use to build chaincode, so chaincode install fails
# with "broken pipe" / "unexpected EOF". /var/lib/docker (images, volumes) is kept.
set -euo pipefail
VER=5:28.3.2-1~ubuntu.22.04~jammy
export DEBIAN_FRONTEND=noninteractive
rm -f /etc/systemd/system/docker.service.d/min-api.conf; systemctl daemon-reload
if [ "$(docker version --format '{{.Server.Version}}' 2>/dev/null)" = "28.3.2" ]; then echo "$(hostname): already 28.3.2"; exit 0; fi
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu jammy stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get remove -y -qq docker.io docker-compose-v2 >/dev/null 2>&1 || true
apt-get install -y -qq --allow-downgrades docker-ce=$VER docker-ce-cli=$VER containerd.io docker-compose-plugin >/dev/null
apt-mark hold docker-ce docker-ce-cli >/dev/null
systemctl enable --now docker >/dev/null
docker version --format "$(hostname): server {{.Server.Version}} min api {{.Server.MinAPIVersion}}"
