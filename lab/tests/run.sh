#!/bin/bash
# usage: tests/run.sh   (lab must be deployed)  -> results/test-<date>.log
cd "$(dirname "$0")/.."
mkdir -p results
LOG=results/test-$(date +%F_%H%M%S).log
exec > >(tee "$LOG") 2>&1

PASS=0; FAIL=0
x() { local n=$1; shift; docker exec "clab-apt-$n" "$@"; }

ok()   { PASS=$((PASS+1)); echo "PASS  $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL  $1"; }
# expect_ok "name" node cmd...   /   expect_fail "name" node cmd...
expect_ok()   { local d=$1; shift; if x "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi; }
expect_fail() { local d=$1; shift; if x "$@" >/dev/null 2>&1; then bad "$d"; else ok "$d"; fi; }
ping_ok()   { expect_ok   "$1" $2 ping -c2 -W1 $3; }
ping_fail() { expect_fail "$1" $2 ping -c2 -W1 $3; }
tcp_ok()    { expect_ok   "$1" $2 nc -z -w2 $3 $4; }
tcp_fail()  { expect_fail "$1" $2 nc -z -w2 $3 $4; }
in_range() { python3 -c "import sys; v=float(sys.argv[1]); sys.exit(0 if float(sys.argv[2])<=v<=float(sys.argv[3]) else 1)" $1 $2 $3; }
mbps() { python3 -c "import sys,json; d=json.load(sys.stdin); print('%.1f'%(d['end']['sum_received']['bits_per_second']/1e6))"; }

NVR=10.20.30.10; NET=198.51.100.8
echo "# apartment-network lab tests  $(date -Is)"
echo "# kernel $(uname -r)"

echo; echo "== 0 sanity: gateways + internet"
ping_ok "room101 -> gw 10.21.1.1" room101 10.21.1.1
ping_ok "room101 -> internet 8.8.8.8" room101 8.8.8.8
ping_ok "room101 -> internet web $NET" room101 $NET
tcp_ok  "room101 -> internet tcp/443" room101 $NET 443

echo; echo "== 1 VLAN isolation"
for t in 10.20.20.50 10.20.30.10 10.20.30.20 10.20.10.50 10.20.10.2 10.20.10.1 10.20.20.1; do
  ping_fail "tenant room101 -> $t blocked (icmp)" room101 $t
done
tcp_fail "tenant -> nvr tcp/443 blocked" room101 $NVR 443
tcp_fail "tenant -> nvr tcp/554 blocked" room101 $NVR 554
ping_fail "tenant -> guest 10.20.40.100 blocked" room101 10.20.40.100
tcp_ok   "staff -> nvr tcp/443 allowed" staff $NVR 443
tcp_ok   "staff -> nvr tcp/554 allowed" staff $NVR 554
for p in 80 22 8080; do tcp_fail "staff -> nvr tcp/$p blocked" staff $NVR $p; done
ping_fail "staff -> nvr icmp blocked" staff $NVR
ping_ok   "staff -> internet" staff 8.8.8.8
ping_fail "staff -> tenant room101 blocked" staff 10.21.1.11
ping_fail "staff -> mgmt-pc blocked" staff 10.20.10.50

echo; echo "== 2 per-room isolation (sw-f1 isolated ports = protected)"
ping_fail "room101 -> room102 ping blocked" room101 10.21.1.12
ping_fail "room102 -> room101 ping blocked" room102 10.21.1.11
ping_fail "room101 -> room103 ping blocked" room101 10.21.1.13
expect_fail "room101 -> room102 arping blocked" room101 arping -c2 -w3 -I eth1 10.21.1.12
expect_fail "room103 -> room102 arping blocked" room103 arping -c2 -w3 -I eth1 10.21.1.12
for r in room101 room102 room103; do
  ping_ok "$r -> gateway" $r 10.21.1.1
  ping_ok "$r -> internet 8.8.8.8" $r 8.8.8.8
done
# control: with isolation off the same ping must work, so the test above means something
for i in 2 3 4; do x sw-f1 bridge link set dev eth$i isolated off; done
x room101 ip neigh flush all
ping_ok "control: isolation off -> room101 reaches room102" room101 10.21.1.12
for i in 2 3 4; do x sw-f1 bridge link set dev eth$i isolated on; done
x room101 ip neigh flush all
ping_fail "isolation restored -> room101 blocked again" room101 10.21.1.12
echo "-- sw-f1 bridge port isolated flag (sysfs):"; for i in 1 2 3 4; do echo "   eth$i isolated=$(x sw-f1 cat /sys/class/net/eth$i/brport/isolated)"; done

echo; echo "== 3 guest internet-only"
ping_ok   "guest -> internet 8.8.8.8" guest 8.8.8.8
tcp_ok    "guest -> internet tcp/80" guest $NET 80
ping_ok   "guest -> own gateway" guest 10.20.40.1
for t in 10.20.10.1 10.20.10.2 10.20.10.50 10.20.20.50 10.20.30.10 10.21.1.11 10.20.20.1 172.16.0.1 192.168.1.1 192.168.100.5; do
  ping_fail "guest -> $t blocked" guest $t
done
tcp_fail "guest -> nvr tcp/443 blocked" guest $NVR 443

echo; echo "== 6 cctv no internet"
ping_fail "cam -> internet 8.8.8.8 blocked" cam 8.8.8.8
tcp_fail  "cam -> internet tcp/80 blocked" cam $NET 80
ping_fail "nvr -> internet 8.8.8.8 blocked" nvr 8.8.8.8
ping_fail "cam -> staff blocked" cam 10.20.20.50
ping_fail "cam -> tenant blocked" cam 10.21.1.11
ping_ok   "cam -> nvr (same vlan)" cam $NVR

echo; echo "== 5 owner VPN"
x owner bash /cfg/vpn-down.sh
for t in 10.20.30.10 10.20.10.1 10.20.10.50 10.20.10.2 10.21.1.11 10.20.20.50 10.20.50.1; do
  ping_fail "no vpn: owner -> $t unreachable" owner $t
done
tcp_fail "no vpn: owner -> nvr tcp/443" owner $NVR 443
ping_ok  "no vpn: owner -> fw wan 203.0.113.2 (public edge only)" owner 203.0.113.2
x owner bash /cfg/vpn-up.sh
sleep 3
echo "-- wg show (fw):"; x fw-edge wg show wg0 | grep -E "peer|endpoint|handshake|transfer" | sed 's/^/   /'
ping_ok  "vpn: owner -> fw tunnel 10.20.50.1" owner 10.20.50.1
ping_ok  "vpn: owner -> fw mgmt 10.20.10.1" owner 10.20.10.1
ping_ok  "vpn: owner -> mgmt-pc 10.20.10.50" owner 10.20.10.50
ping_ok  "vpn: owner -> sw-core mgmt 10.20.10.2" owner 10.20.10.2
ping_ok  "vpn: owner -> sw-f1 mgmt 10.20.10.11" owner 10.20.10.11
ping_ok  "vpn: owner -> nvr 10.20.30.10" owner $NVR
tcp_ok   "vpn: owner -> nvr tcp/443" owner $NVR 443
tcp_ok   "vpn: owner -> nvr tcp/554" owner $NVR 554
ping_fail "vpn: owner -> tenant 10.21.1.11 blocked (no route)" owner 10.21.1.11
ping_fail "vpn: owner -> staff 10.20.20.50 blocked (no route)" owner 10.20.20.50
# force routes through the tunnel and let the firewall prove it drops them
x fw-edge wg set wg0 peer "$(x owner cat /etc/wg/owner.pub)" allowed-ips 10.20.50.2/32
x owner wg set wg0 peer "$(x owner cat /etc/wg/fw.pub)" allowed-ips 10.20.50.1/32,10.20.10.0/24,10.20.30.0/24,10.21.1.0/24,10.20.20.0/24,10.20.40.0/24
x owner ip route replace 10.21.1.0/24 dev wg0
x owner ip route replace 10.20.20.0/24 dev wg0
x owner ip route replace 10.20.40.0/24 dev wg0
ping_fail "vpn forced route: owner -> tenant 10.21.1.11 dropped by fw" owner 10.21.1.11
ping_fail "vpn forced route: owner -> staff 10.20.20.50 dropped by fw" owner 10.20.20.50
ping_fail "vpn forced route: owner -> guest 10.20.40.100 dropped by fw" owner 10.20.40.100
x owner bash /cfg/vpn-down.sh
ping_fail "vpn down again: owner -> nvr unreachable" owner $NVR

echo; echo "== 4 bandwidth (iperf3 -> internet $NET, 8s)"
bw() {  # label node expect_down_lo hi expect_up_lo hi
  local up down
  up=$(x $2 iperf3 -c $NET -t 8 -J | mbps)
  down=$(x $2 iperf3 -c $NET -t 8 -R -J | mbps)
  echo "MEASURED $1 upload=${up} Mbps download=${down} Mbps"
  if in_range "$down" $3 $4; then ok "$1 download ${down} Mbps within [$3,$4]"; else bad "$1 download ${down} Mbps outside [$3,$4]"; fi
  if in_range "$up"   $5 $6; then ok "$1 upload ${up} Mbps within [$5,$6]";   else bad "$1 upload ${up} Mbps outside [$5,$6]"; fi
}
bw "tenant room101 (plan 100/50)" room101 85 105 40 53
bw "tenant room102 (plan 100/50)" room102 85 105 40 53
bw "guest (plan 20/10)" guest 17 21 8 11
echo "-- fw tc stats ifb0 (upload, room101):"; x fw-edge tc -s class show dev ifb0 | grep -A1 "class htb 1:11 " | sed 's/^/   /'

echo; echo "-- nft counters on fw (drops that proved the policy):"
x fw-edge nft list chain inet fw forward | grep counter | grep -v "packets 0 " | sed 's/^/   /'

echo
echo "SUMMARY $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
