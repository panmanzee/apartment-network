#!/bin/bash
# eth1 uplink trunk, eth2-4 = Gi1/0/1-3 (rooms 101-103), untagged vlan 101, isolated (= protected)
ip link add br0 type bridge vlan_filtering 1
ip link set br0 up
for i in 1 2 3 4; do ip link set eth$i master br0; ip link set eth$i up; bridge vlan del vid 1 dev eth$i; done
bridge vlan add vid 10 dev eth1
bridge vlan add vid 101 dev eth1
for i in 2 3 4; do
  bridge vlan add vid 101 dev eth$i pvid untagged
  bridge link set dev eth$i isolated on
done
bridge vlan add vid 10 dev br0 self
ip link add link br0 name br0.10 type vlan id 10
ip link set br0.10 up
ip addr add 10.20.10.11/24 dev br0.10
ip route replace default via 10.20.10.1
