#!/bin/bash
# runs inside owner: bring up wg0 to the firewall (203.0.113.2:51820)
ip link add wg0 type wireguard 2>/dev/null || true
ip addr replace 10.20.50.2/24 dev wg0
wg set wg0 private-key /etc/wg/owner.key \
  peer "$(cat /etc/wg/fw.pub)" endpoint 203.0.113.2:51820 \
  allowed-ips 10.20.50.1/32,10.20.10.0/24,10.20.30.0/24 persistent-keepalive 5
ip link set wg0 up
ip route replace 10.20.10.0/24 dev wg0
ip route replace 10.20.30.0/24 dev wg0
