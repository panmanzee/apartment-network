#!/bin/bash
# build image, deploy containerlab topology, exchange wireguard keys
set -e
cd "$(dirname "$0")"
if ! command -v containerlab >/dev/null; then
  bash -c "$(curl -sL https://get.containerlab.dev)"
fi
modprobe ifb 2>/dev/null || true
docker image inspect apt-lab:latest >/dev/null 2>&1 || docker build -t apt-lab:latest .
containerlab deploy -t apartment.clab.yml --reconfigure

# owner keypair, fw learns owner pubkey, owner learns fw pubkey
docker exec clab-apt-owner bash -c 'umask 077; mkdir -p /etc/wg; wg genkey | tee /etc/wg/owner.key | wg pubkey > /etc/wg/owner.pub'
OPUB=$(docker exec clab-apt-owner cat /etc/wg/owner.pub)
FPUB=$(docker exec clab-apt-fw-edge cat /etc/wg/fw.pub)
docker exec clab-apt-fw-edge wg set wg0 peer "$OPUB" allowed-ips 10.20.50.2/32
docker exec clab-apt-owner bash -c "echo $FPUB > /etc/wg/fw.pub"
echo "deployed"
