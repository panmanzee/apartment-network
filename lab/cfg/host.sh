#!/bin/bash
# $1 = addr/mask, $2 = gateway
ip link set eth1 up
ip addr add "$1" dev eth1
ip route replace default via "$2" dev eth1
