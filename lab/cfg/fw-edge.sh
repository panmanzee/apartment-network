#!/bin/bash
sysctl -qw net.ipv4.ip_forward=1
sysctl -qw net.ipv4.conf.all.rp_filter=0

ip link set eth1 up; ip link set eth2 up
ip addr add 203.0.113.2/30 dev eth2
ip route replace default via 203.0.113.1 dev eth2

add_vlan() {  # id addr
  ip link add link eth1 name vlan$1 type vlan id $1
  ip addr add $2 dev vlan$1
  ip link set vlan$1 up
}
add_vlan 10  10.20.10.1/24
add_vlan 20  10.20.20.1/24
add_vlan 30  10.20.30.1/24
add_vlan 40  10.20.40.1/24
add_vlan 101 10.21.1.1/24

# wireguard for the owner
mkdir -p /etc/wg
umask 077
wg genkey | tee /etc/wg/fw.key | wg pubkey > /etc/wg/fw.pub
ip link add wg0 type wireguard
ip addr add 10.20.50.1/24 dev wg0
wg set wg0 listen-port 51820 private-key /etc/wg/fw.key
ip link set wg0 up

nft -f /cfg/fw.nft
bash /cfg/shape.sh
