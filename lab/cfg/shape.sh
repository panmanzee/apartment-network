#!/bin/bash
# per-client shaping on the firewall
# down (toward the client): htb on the vlan interface egress
# up (from the client): ingress redirected to an ifb device, htb there
shape() {  # dev ifb prefix first last down_mbit up_mbit
  local dev=$1 ifb=$2 pre=$3 a=$4 b=$5 down=$6 up=$7 i
  ip link add $ifb type ifb
  ip link set $ifb up
  tc qdisc add dev $dev root handle 1: htb default 999
  tc class add dev $dev parent 1: classid 1:999 htb rate 1000mbit
  tc qdisc add dev $ifb root handle 1: htb default 999
  tc class add dev $ifb parent 1: classid 1:999 htb rate 1000mbit
  tc qdisc add dev $dev handle ffff: ingress
  tc filter add dev $dev parent ffff: protocol ip prio 1 u32 match u32 0 0 \
    action mirred egress redirect dev $ifb
  for i in $(seq $a $b); do
    tc class add dev $dev parent 1: classid 1:$i htb rate ${down}mbit ceil ${down}mbit
    tc qdisc add dev $dev parent 1:$i fq_codel
    tc filter add dev $dev parent 1: protocol ip prio 1 u32 match ip dst $pre.$i/32 flowid 1:$i
    tc class add dev $ifb parent 1: classid 1:$i htb rate ${up}mbit ceil ${up}mbit
    tc qdisc add dev $ifb parent 1:$i fq_codel
    tc filter add dev $ifb parent 1: protocol ip prio 1 u32 match ip src $pre.$i/32 flowid 1:$i
  done
}
# rooms 101-112 -> 10.21.1.11-22 ; guests -> 10.20.40.100-139
shape vlan101 ifb0 10.21.1 11 22 100 50
shape vlan40  ifb1 10.20.40 100 139 20 10
