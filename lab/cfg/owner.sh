#!/bin/bash
ip link set eth1 up
ip addr add 192.0.2.10/24 dev eth1
ip route replace default via 192.0.2.1 dev eth1
