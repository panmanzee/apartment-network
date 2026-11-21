#!/usr/bin/env python3
"""Static checks on the rendered configs against plan/ip-plan.yaml. No device is contacted."""
import datetime
import ipaddress
import shlex
import sys
from pathlib import Path

import yaml
from ciscoconfparse2 import CiscoConfParse

HERE = Path(__file__).resolve().parent
PLAN = yaml.safe_load((HERE.parent / "plan" / "ip-plan.yaml").read_text())
OUT = HERE / "out"
BLACKHOLE = 999

results = []


def check(scope, desc, ok):
    results.append((bool(ok), scope, desc))


def vlan_set(text):
    s = set()
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            s |= set(range(int(a), int(b) + 1))
        else:
            s.add(int(part))
    return s


def gi(n):
    return f"GigabitEthernet1/0/{n}"


def ios_ports(conf):
    ports = {}
    for obj in conf.find_objects(r"^interface "):
        name = obj.text.split(None, 1)[1]
        ports[name] = [c.text.strip() for c in obj.children]
    return ports


def val(lines, prefix):
    for l in lines:
        if l.startswith(prefix):
            return l[len(prefix):].strip()
    return None


def common_ios(host, path, text, conf, dev):
    s = host
    check(s, "hostname matches plan", f"hostname {dev['name']}" in text.splitlines())
    check(s, "rapid-pvst", "spanning-tree mode rapid-pvst" in text)
    check(s, "no telnet anywhere", "telnet" not in text.lower())
    vty = conf.find_objects(r"^line vty")
    check(s, "vty transport input ssh only",
          vty and all(" transport input ssh" in [" " + c.text.strip() for c in v.children]
                      and not any("transport input" in c.text and c.text.strip() != "transport input ssh"
                                  for c in v.children) for v in vty))
    check(s, "vty access-class applied", all(any(c.text.strip().startswith("access-class") for c in v.children) for v in vty))
    check(s, "ssh v2", "ip ssh version 2" in text)
    check(s, "http server off", "no ip http server" in text and "no ip http secure-server" in text)
    check(s, "aaa local login", "aaa authentication login default local" in text)
    check(s, "snmp v3 only (no community)", "snmp-server community" not in text and " v3 auth sha " in text
          and "snmp-server group G-NMS v3 priv" in text)
    check(s, "ntp server is fw", "ntp server 10.20.10.1" in text)
    check(s, "logging host set", any(l.startswith("logging host ") for l in text.splitlines()))
    check(s, "banner present", "banner motd ^C" in text)
    check(s, "secrets are placeholders, none in clear",
          all("__" in l for l in text.splitlines() if " secret " in l))
    ports = ios_ports(conf)
    svi = ports.get("Vlan10", [])
    check(s, f"mgmt SVI {dev['mgmt_ip']}", f"ip address {dev['mgmt_ip']} 255.255.255.0" in svi)
    return ports


def check_access(dev):
    name = dev["name"]
    n = dev["floor"]
    tv = 100 + n
    path = OUT / "cisco" / f"{name}.cfg"
    text = path.read_text()
    conf = CiscoConfParse(str(path), syntax="ios")
    ports = common_ios(name, path, text, conf, dev)
    ap = PLAN["access_ports"]
    check(name, "not stp root (no priority 4096)", "priority 4096" not in text)
    # room ports
    for i in range(1, ap["room_ports"] + 1):
        p = ports.get(gi(i), [])
        room = n * 100 + i
        ok = (val(p, "description ") == f"room-{room}"
              and "switchport mode access" in p and f"switchport access vlan {tv}" in p
              and "switchport protected" in p and "switchport port-security" in p
              and "switchport port-security violation restrict" in p
              and any(l.startswith("switchport port-security maximum") for l in p)
              and any(l.startswith("storm-control broadcast level") for l in p)
              and "spanning-tree portfast" in p and "spanning-tree bpduguard enable" in p
              and "shutdown" not in p)
        check(name, f"room {room} on Gi1/0/{i}: access vlan {tv}, protected, port-sec, storm, bpduguard", ok)
    tenant_ports = [k for k, v in ports.items() if f"switchport access vlan {tv}" in v]
    check(name, f"exactly {ap['room_ports']} ports in vlan {tv}", len(tenant_ports) == ap["room_ports"])
    # APs
    aps = sorted(d["name"] for d in PLAN["devices"] if d["role"] == "ap" and d.get("floor") == n)
    for apname, pn in zip(aps, ap["ap_ports"]):
        p = ports.get(gi(pn), [])
        allowed = vlan_set(val(p, "switchport trunk allowed vlan ") or "0")
        check(name, f"{apname} Gi1/0/{pn} trunk native 10 allowed {{10,40,{tv}}}",
              "switchport mode trunk" in p and "switchport trunk native vlan 10" in p
              and allowed == {10, 40, tv} and val(p, "description ") == apname)
    # cctv
    for pn in ap["cctv_ports"]:
        p = ports.get(gi(pn), [])
        check(name, f"cctv Gi1/0/{pn} access vlan 30 + bpduguard",
              "switchport access vlan 30" in p and "spanning-tree bpduguard enable" in p
              and "switchport port-security" in p)
    # uplink
    up = ports.get(gi(ap["uplink"]), [])
    allowed = vlan_set(val(up, "switchport trunk allowed vlan ") or "0")
    check(name, f"uplink Gi1/0/{ap['uplink']} trunk allowed exactly {{10,30,40,{tv}}}",
          "switchport mode trunk" in up and allowed == {10, 30, 40, tv})
    check(name, "uplink never carries staff/other floors' tenant vlans", not (allowed & {20, 101, 102, 103, 104, 105} - {tv}))
    check(name, "uplink native vlan is blackhole", f"switchport trunk native vlan {BLACKHOLE}" in up)
    check(name, "uplink dhcp snooping trust", "ip dhcp snooping trust" in up)
    check(name, "no 'allowed vlan all'", "allowed vlan all" not in text)
    # spare
    used = set(range(1, ap["room_ports"] + 1)) | set(ap["ap_ports"]) | set(ap["cctv_ports"]) | {ap["uplink"]}
    spare = [p for p in range(1, 25) if p not in used]
    check(name, f"spare ports {spare[0]}-{spare[-1]} shutdown in blackhole vlan",
          all("shutdown" in ports.get(gi(p), []) and f"switchport access vlan {BLACKHOLE}" in ports.get(gi(p), []) for p in spare))
    check(name, "all 24 ports configured", all(gi(p) in ports for p in range(1, 25)))
    check(name, "vlan list is only 10,30,40,tenant,999",
          {int(o.text.split()[1]) for o in conf.find_objects(r"^vlan \d+")} == {10, 30, 40, tv, BLACKHOLE})
    check(name, "dhcp snooping vlans", f"ip dhcp snooping vlan 40,{tv}" in text)


def check_core(dev):
    name = "sw-core"
    path = OUT / "cisco" / "sw-core.cfg"
    text = path.read_text()
    conf = CiscoConfParse(str(path), syntax="ios")
    ports = common_ios(name, path, text, conf, dev)
    all_ids = {v["id"] for v in PLAN["vlans"]}
    check(name, "stp root priority 4096 on all vlans", "spanning-tree vlan 1-4094 priority 4096" in text)
    check(name, "no ip routing (l2 only)", "no ip routing" in text)
    check(name, "default gateway is fw", "ip default-gateway 10.20.10.1" in text)
    check(name, "all plan vlans defined",
          {int(o.text.split()[1]) for o in conf.find_objects(r"^vlan \d+")} == all_ids | {BLACKHOLE})
    po = ports.get("Port-channel1", [])
    check(name, "Po1 trunk allowed = all plan vlans", vlan_set(val(po, "switchport trunk allowed vlan ") or "0") == all_ids)
    for pn in (1, 2):
        p = ports.get(gi(pn), [])
        check(name, f"Gi1/0/{pn} in channel-group 1 (lacp active)", "channel-group 1 mode active" in p)
    for n in range(1, PLAN["site"]["floors"] + 1):
        p = ports.get(gi(10 + n), [])
        a = vlan_set(val(p, "switchport trunk allowed vlan ") or "0")
        acc = vlan_set(val(ios_ports(CiscoConfParse(str(OUT / "cisco" / f"sw-f{n}.cfg"), syntax="ios")).get(gi(24), []),
                           "switchport trunk allowed vlan ") or "0")
        check(name, f"Gi1/0/{10 + n} -> sw-f{n} trunk list equals sw-f{n} uplink list {sorted(a)}",
              "switchport mode trunk" in p and a == acc == {10, 30, 40, 100 + n})
    cctv = [k for k, v in ports.items() if "switchport access vlan 30" in v]
    check(name, "nvr + 4 lobby cctv ports in vlan 30", len(cctv) == 5)
    check(name, "staff ports in vlan 20", sum("switchport access vlan 20" in v for v in ports.values()) == 4)
    ap = ports.get(gi(6), [])
    check(name, "ap-lobby trunk native 10 allowed {10,40}",
          "switchport trunk native vlan 10" in ap and vlan_set(val(ap, "switchport trunk allowed vlan ") or "0") == {10, 40})
    check(name, "no tenant vlan reaches core access ports",
          not any(any(f"switchport access vlan {t}" in v for t in range(101, 106)) for v in ports.values()))
    check(name, "all 24 ports configured", all(gi(p) in ports for p in range(1, 25)))


# fortios

def parse_fos(text):
    root = {"_": {}}
    stack = [root]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        t = shlex.split(line)
        cur = stack[-1]
        if t[0] == "config":
            node = cur.setdefault(" ".join(t[1:]), {"_": {}})
            stack.append(node)
        elif t[0] == "edit":
            node = cur.setdefault(t[1], {"_": {}})
            stack.append(node)
        elif t[0] in ("next", "end"):
            stack.pop()
        elif t[0] == "set":
            cur["_"][t[1]] = t[2:]
    return root


BUILTIN = {"HTTPS": {443}, "HTTP": {80}, "DNS": {53}, "NTP": {123}}


def fos_eval(fos, src_if, src_ip, dst_ip, port):
    vlans = {v["name"]: v for v in PLAN["vlans"]}
    ifs = {f"v{v['id']}-{v['name'].lower()}": ipaddress.ip_network(v["subnet"]) for v in PLAN["vlans"]}
    dip = ipaddress.ip_address(dst_ip)
    dst_if = next((n for n, net in ifs.items() if dip in net), None)
    if dst_if is None:
        dst_if = "owner-vpn-a" if dip in ipaddress.ip_network(PLAN["vpn"]["owner"]["pool"]) else "virtual-wan-link"
    addrs = {}
    for k, v in fos["firewall address"].items():
        if k != "_":
            addrs[k] = ipaddress.ip_network("/".join([v["_"]["subnet"][0], v["_"]["subnet"][1]]))
    grps = {k: v["_"]["member"] for k, v in fos.get("firewall addrgrp", {}).items() if k != "_"}
    svcs = {k: {int(p) for p in v["_"]["tcp-portrange"]} for k, v in fos["firewall service custom"].items() if k != "_"}
    sgrp = {k: v["_"]["member"] for k, v in fos["firewall service group"].items() if k != "_"}

    def addr_match(names, ip):
        for nme in names:
            if nme == "all":
                return True
            members = grps.get(nme, [nme])
            if any(ip in addrs[m] for m in members):
                return True
        return False

    def svc_match(names):
        for nme in names:
            if nme == "ALL":
                return True
            if nme in svcs and port in svcs[nme]:
                return True
            for m in sgrp.get(nme, []):
                if port in BUILTIN.get(m, set()):
                    return True
        return False

    for pid, pol in fos["firewall policy"].items():
        if pid == "_":
            continue
        s = pol["_"]
        if (("any" in s["srcintf"] or src_if in s["srcintf"]) and ("any" in s["dstintf"] or dst_if in s["dstintf"])
                and addr_match(s["srcaddr"], ipaddress.ip_address(src_ip)) and addr_match(s["dstaddr"], dip)
                and svc_match(s["service"])):
            return s["action"][0], s["name"][0]
    return "deny", "implicit"


def check_fortigate():
    s = "fw-edge"
    text = (OUT / "fortigate" / "fw-edge.conf").read_text()
    fos = parse_fos(text)
    ifc = fos["system interface"]
    for v in PLAN["vlans"]:
        n = f"v{v['id']}-{v['name'].lower()}"
        i = ifc.get(n, {"_": {}})["_"]
        net = ipaddress.ip_network(v["subnet"])
        check(s, f"{n}: vlanid {v['id']}, ip {v['gw']}/{net.prefixlen} on lag-core",
              i.get("vlanid") == [str(v["id"])] and i.get("interface") == ["lag-core"]
              and i.get("ip") == [v["gw"], str(net.netmask)])
        acc = set(i.get("allowaccess", []))
        if v["name"] == "MGMT":
            check(s, "admin access (https/ssh/snmp) only on MGMT interface", {"https", "ssh", "snmp"} <= acc)
        else:
            check(s, f"{n}: no admin access", not (acc & {"https", "ssh", "http", "telnet", "snmp", "fgfm"}))
    check(s, "lag-core aggregate with lacp active",
          ifc["lag-core"]["_"].get("type") == ["aggregate"] and ifc["lag-core"]["_"].get("lacp-mode") == ["active"])
    check(s, "wan interfaces: no admin access",
          all(not (set(ifc[w]["_"].get("allowaccess", [])) & {"https", "ssh", "http", "telnet"}) for w in ("wan1", "wan2")))
    guest = ifc["v40-guest"]["_"]
    check(s, "captive portal on GUEST", guest.get("security-mode") == ["captive-portal"])
    # dhcp
    dhcp = fos["system dhcp server"]
    dif = {v["_"]["interface"][0] for k, v in dhcp.items() if k != "_"}
    want = {f"v{v['id']}-{v['name'].lower()}" for v in PLAN["vlans"] if v["dhcp"]}
    check(s, f"dhcp servers exactly on dhcp:true vlans ({len(want)})", dif == want)
    # admin
    adm = [v for k, v in fos["system admin"].items() if k != "_"]
    check(s, "admin trusthost = MGMT subnet only",
          all(a["_"].get("trusthost1") == ["10.20.10.0", "255.255.255.0"] and "trusthost2" not in a["_"] for a in adm))
    check(s, "admin lockout + tls1.2+",
          "admin-lockout-threshold" in fos["system global"]["_"]
          and fos["system global"]["_"]["admin-https-ssl-versions"] == ["tlsv1-2", "tlsv1-3"])
    # snmp
    su = [v for k, v in fos["system snmp user"].items() if k != "_"]
    check(s, "snmp v3 auth-priv user, no community", len(su) == 1 and su[0]["_"]["security-level"] == ["auth-priv"]
          and "system snmp community" not in fos)
    # sdwan
    sd = fos["system sdwan"]
    mem = [v["_"]["interface"][0] for k, v in sd["members"].items() if k != "_"]
    check(s, "sd-wan members wan1+wan2 with health-check", mem == ["wan1", "wan2"] and "hc-internet" in sd["health-check"])
    check(s, "static default via sd-wan zone", fos["router static"]["1"]["_"]["sdwan-zone"] == ["virtual-wan-link"])
    # vpn
    pool = ipaddress.ip_network(PLAN["vpn"]["owner"]["pool"])
    p1 = {k: v for k, v in fos["vpn ipsec phase1-interface"].items() if k != "_"}
    p2 = {k: v["_"]["phase1name"][0] for k, v in fos["vpn ipsec phase2-interface"].items() if k != "_"}
    check(s, "dial-up ipsec phase1 on each wan, dynamic, in pool",
          len(p1) == 2 and all(v["_"]["type"] == ["dynamic"]
                               and ipaddress.ip_address(v["_"]["ipv4-start-ip"][0]) in pool
                               and ipaddress.ip_address(v["_"]["ipv4-end-ip"][0]) in pool for v in p1.values()))
    check(s, "phase2 for every phase1", set(p2.values()) == set(p1))
    split = fos["firewall addrgrp"]["grp-vpn-allowed"]["_"]["member"]
    allowed = {f"net-{n}" for n in PLAN["vpn"]["owner"]["allowed"]}
    check(s, "vpn split-include = MGMT+CCTV only", set(split) == allowed
          and all(v["_"]["ipv4-split-include"] == ["grp-vpn-allowed"] for v in p1.values()))
    # policies from yaml
    pols = {k: v["_"] for k, v in fos["firewall policy"].items() if k != "_"}
    for idx, r in enumerate(PLAN["policy"], 1):
        hits = [p for p in pols.values() if p.get("comments", [""])[0].startswith(f"plan policy {idx}:")]
        act = "accept" if r["action"] == "allow" else "deny"
        check(s, f"yaml policy {idx} ({r['src']} -> {r['dst']} {r['action']}) has policy with action {act}",
              len(hits) >= 1 and all(h["action"] == [act] for h in hits))
    check(s, "last policy is catch-all deny", list(pols.values())[-1]["action"] == ["deny"])
    check(s, "nat only on internet-bound accepts",
          all((p.get("nat") == ["enable"]) == ("virtual-wan-link" in p["dstintf"]) for p in pols.values() if p["action"] == ["accept"]))
    # shapers
    shp = {k: v["_"] for k, v in fos["firewall shaper per-ip-shaper"].items() if k != "_"}
    sp = {k: v["_"] for k, v in fos["firewall shaping-policy"].items() if k != "_"}
    for r in PLAN["policy"]:
        if "shape" in r:
            down = int(r["shape"].split("/")[0]) * 1000
            ok = any(shp[p["per-ip-shaper"][0]]["max-bandwidth"] == [str(down)] and p["dstintf"] == ["virtual-wan-link"]
                     and (("grp-tenants" in p["srcaddr"]) if r["src"] == "TENANT-*" else ("net-" + r["src"] in p["srcaddr"]))
                     for p in sp.values())
            check(s, f"per-ip shaper {r['src']} {r['shape']}: shaping-policy applied at {down} kbps", ok)
    # flow tests (first-match simulation)
    t = lambda n: f"v{100 + n}-tenant-f{n}"
    flows = [
        ("tenant f1 -> internet 443", t(1), "10.21.1.60", "8.8.8.8", 443, "accept"),
        ("tenant f1 -> tenant f2", t(1), "10.21.1.60", "10.21.2.60", 80, "deny"),
        ("tenant f3 -> tenant f5", t(3), "10.21.3.60", "10.21.5.9", 22, "deny"),
        ("tenant -> MGMT", t(2), "10.21.2.60", "10.20.10.2", 22, "deny"),
        ("tenant -> STAFF", t(2), "10.21.2.60", "10.20.20.5", 445, "deny"),
        ("tenant -> CCTV nvr", t(4), "10.21.4.60", "10.20.30.10", 443, "deny"),
        ("tenant -> GUEST", t(5), "10.21.5.60", "10.20.40.50", 80, "deny"),
        ("guest -> internet", "v40-guest", "10.20.40.60", "8.8.8.8", 443, "accept"),
        ("guest -> MGMT", "v40-guest", "10.20.40.60", "10.20.10.1", 443, "deny"),
        ("guest -> STAFF", "v40-guest", "10.20.40.60", "10.20.20.10", 80, "deny"),
        ("guest -> 172.16.0.1", "v40-guest", "10.20.40.60", "172.16.0.1", 80, "deny"),
        ("guest -> tenant", "v40-guest", "10.20.40.60", "10.21.1.60", 80, "deny"),
        ("staff -> internet", "v20-staff", "10.20.20.60", "8.8.8.8", 443, "accept"),
        ("staff -> cctv 443", "v20-staff", "10.20.20.60", "10.20.30.10", 443, "accept"),
        ("staff -> cctv 554", "v20-staff", "10.20.20.60", "10.20.30.11", 554, "accept"),
        ("staff -> cctv 22", "v20-staff", "10.20.20.60", "10.20.30.10", 22, "deny"),
        ("staff -> MGMT", "v20-staff", "10.20.20.60", "10.20.10.2", 22, "deny"),
        ("staff -> tenant", "v20-staff", "10.20.20.60", "10.21.1.60", 80, "deny"),
        ("cctv -> internet", "v30-cctv", "10.20.30.20", "8.8.8.8", 443, "deny"),
        ("cctv -> staff", "v30-cctv", "10.20.30.20", "10.20.20.5", 445, "deny"),
        ("vpn -> MGMT", "owner-vpn-a", "10.20.50.20", "10.20.10.2", 22, "accept"),
        ("vpn(b) -> CCTV", "owner-vpn-b", "10.20.50.20", "10.20.30.10", 443, "accept"),
        ("vpn -> STAFF", "owner-vpn-a", "10.20.50.20", "10.20.20.5", 445, "deny"),
        ("vpn -> tenant", "owner-vpn-a", "10.20.50.20", "10.21.1.60", 80, "deny"),
        ("vpn -> internet", "owner-vpn-a", "10.20.50.20", "8.8.8.8", 443, "deny"),
        ("mgmt -> internet 443", "v10-mgmt", "10.20.10.2", "8.8.8.8", 443, "accept"),
        ("mgmt -> internet 22", "v10-mgmt", "10.20.10.2", "8.8.8.8", 22, "deny"),
        ("mgmt -> tenant", "v10-mgmt", "10.20.10.2", "10.21.1.60", 80, "deny"),
    ]
    for desc, si, sip, dip, port, exp in flows:
        got, pol = fos_eval(fos, si, sip, dip, port)
        check(s, f"flow {desc}: {exp}" + ("" if got == exp else f" (got {got} via {pol})"), got == exp)


def main():
    devs = {d["name"]: d for d in PLAN["devices"]}
    check_core(devs["sw-core"])
    for d in PLAN["devices"]:
        if d["role"] == "access-switch":
            check_access(d)
    check_fortigate()
    lines = [f"{'PASS' if ok else 'FAIL'}  {scope:8} {desc}" for ok, scope, desc in results]
    failed = sum(1 for ok, _, _ in results if not ok)
    lines.append(f"\n{len(results) - failed}/{len(results)} checks passed, {failed} failed")
    text = "\n".join(lines) + "\n"
    log = HERE / "results" / f"check-{datetime.date.today().isoformat()}.log"
    log.parent.mkdir(exist_ok=True)
    log.write_text(text)
    print(text, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
