#!/bin/bash
ip link set eth1 up
ip addr add 198.51.100.8/24 dev eth1
ip addr add 8.8.8.8/32 dev lo
ip route replace default via 198.51.100.1 dev eth1
nohup iperf3 -s >/dev/null 2>&1 &
for p in 80 443; do nohup socat TCP-LISTEN:$p,fork,reuseaddr SYSTEM:"echo web:$p" >/dev/null 2>&1 & done
