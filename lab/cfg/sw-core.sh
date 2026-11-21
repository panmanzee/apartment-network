#!/bin/bash
# eth1 trunk to fw, eth2 trunk to sw-f1, eth3 staff(20), eth4 guest(40), eth5 cam(30), eth6 nvr(30), eth7 mgmt(10)
ip link add br0 type bridge vlan_filtering 1
ip link set br0 up
for i in 1 2 3 4 5 6 7; do ip link set eth$i master br0; ip link set eth$i up; bridge vlan del vid 1 dev eth$i; done
for v in 10 20 30 40 101; do
  bridge vlan add vid $v dev eth1
  bridge vlan add vid $v dev eth2
done
bridge vlan add vid 20 dev eth3 pvid untagged
bridge vlan add vid 40 dev eth4 pvid untagged
bridge vlan add vid 30 dev eth5 pvid untagged
bridge vlan add vid 30 dev eth6 pvid untagged
bridge vlan add vid 10 dev eth7 pvid untagged
bridge vlan add vid 10 dev br0 self
ip link add link br0 name br0.10 type vlan id 10
ip link set br0.10 up
ip addr add 10.20.10.2/24 dev br0.10
ip route replace default via 10.20.10.1
