#!/bin/bash
sysctl -qw net.ipv4.ip_forward=1
ip link set eth1 up; ip link set eth2 up; ip link set eth3 up
ip addr add 203.0.113.1/30 dev eth1
ip addr add 198.51.100.1/24 dev eth2
ip addr add 192.0.2.1/24 dev eth3
ip route add 8.8.8.8/32 via 198.51.100.8
