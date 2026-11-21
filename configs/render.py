#!/usr/bin/env python3
"""Render FortiOS + Cisco IOS configs and the ansible inventory from plan/ip-plan.yaml."""
import ipaddress
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).resolve().parent
PLAN = HERE.parent / "plan" / "ip-plan.yaml"
OUT = HERE / "out"

# values that are not in the plan yaml
EXTRA = {
    "domain": "baan-chalong.lan",
    "admin_user": "netadmin",
    "owner_user": "owner",
    "snmp_user": "nms",
    "contact": "netadmin@baan-chalong.lan",
    "syslog_host": "10.20.10.50",
    "nms_host": "10.20.10.50",
    "upstream_ntp": ["th.pool.ntp.org", "time.google.com"],
    "blackhole_vlan": 999,
    "banner": ("Authorized access only. Activity is logged.\n"
               "Baan Chalong Residence network - disconnect if you are not staff."),
}
FW_LAG = ["internal1", "internal2"]
WANS = [("wan1", "ISP-A primary"), ("wan2", "ISP-B backup")]
RFC1918 = [("rfc1918-10", "10.0.0.0/8"), ("rfc1918-172", "172.16.0.0/12"),
           ("rfc1918-192", "192.168.0.0/16")]
# core port map (not in the plan)
CORE = {"fw": [1, 2], "mon": 3, "admin": 4, "nvr": 5, "lobby_ap": 6, "lobby_cctv": [7, 8, 9, 10],
        "floor_base": 10, "staff": [17, 18, 19, 20]}
PORTS = 24


def gi(n):
    return f"GigabitEthernet1/0/{n}"


def netinfo(cidr):
    return ipaddress.ip_network(cidr)


def load():
    return yaml.safe_load(PLAN.read_text())


def build_vlans(plan):
    out = []
    for v in plan["vlans"]:
        n = netinfo(v["subnet"])
        base = str(n.network_address).rsplit(".", 1)[0]
        out.append({
            "id": v["id"], "name": v["name"], "gw": v["gw"], "dhcp": v["dhcp"],
            "ifname": f"v{v['id']}-{v['name'].lower()}",
            "subnet_ip": str(n.network_address), "mask": str(n.netmask),
            "pool_start": f"{base}.50", "pool_end": f"{base}.250",
            "lease": 7200 if v["name"] == "GUEST" else 86400,
        })
    return out


def expand_policies(plan, vlans, vpn_ifs):
    by_name = {v["name"]: v for v in vlans}
    tenants = [v for v in vlans if v["name"].startswith("TENANT-")]
    services, shapers, shaping, policies = {}, {}, [], []

    def ref(name):
        if name == "TENANT-*":
            return [v["ifname"] for v in tenants], ["grp-tenants"]
        if name == "internet":
            return ["virtual-wan-link"], ["all"]
        if name == "rfc1918":
            return ["any"], ["grp-rfc1918"]
        if name == "OWNER-VPN":
            return [p["name"] for p in vpn_ifs], ["net-OWNER-VPN"]
        v = by_name[name]
        return [v["ifname"]], [f"net-{name}"]

    for idx, r in enumerate(plan["policy"], 1):
        srcs = [r["src"]]
        dsts = r["dst"] if isinstance(r["dst"], list) else [r["dst"]]
        si, sa = ref(r["src"])
        di, da = [], []
        for d in dsts:
            i, a = ref(d)
            di += i
            da += a
        svc = ["ALL"]
        if "ports" in r:
            sname = "svc-tcp-" + "-".join(str(p) for p in r["ports"])
            services[sname] = r["ports"]
            svc = [sname]
        if r.get("note", "").startswith("firmware"):
            svc = ["grp-mgmt-out"]
        accept = r["action"] == "allow"
        d_txt = "+".join(dsts)
        d_lbl = d_txt if len(d_txt) <= 14 else "internal"
        policies.append({
            "name": f"p{idx:02d}-{r['src']}-to-{d_lbl}".replace("*", "all")[:35],
            "comment": f"plan policy {idx}: {r['src']} -> {d_txt} {r['action']}",
            "srcintf": si, "dstintf": di, "srcaddr": sa, "dstaddr": da,
            "service": svc, "action": "accept" if accept else "deny",
            "nat": accept and dsts == ["internet"],
            "idx": idx,
        })
        if "shape" in r:
            down = int(r["shape"].split("/")[0]) * 1000
            sname = "shp-" + r["src"].lower().replace("-*", "")
            shapers[sname] = down
            shaping.append({"name": f"shape-{r['src'].lower().replace('-*', '')}",
                            "comment": f"plan policy {idx}: {r['shape']}",
                            "srcaddr": sa, "shaper": sname})
    policies.sort(key=lambda p: p["action"] != "deny")
    policies.append({
        "name": "deny-all-log", "comment": "catch-all", "srcintf": ["any"],
        "dstintf": ["any"], "srcaddr": ["all"], "dstaddr": ["all"],
        "service": ["ALL"], "action": "deny", "nat": False, "idx": 0})
    return (policies, [{"name": k, "ports": v} for k, v in services.items()],
            [{"name": k, "kbps": v} for k, v in shapers.items()], shaping)


def fortigate(plan, env, site):
    vlans = build_vlans(plan)
    vpn_net = netinfo(plan["vpn"]["owner"]["pool"])
    vpn = {"net": str(vpn_net.network_address), "mask": str(vpn_net.netmask),
           "start": str(vpn_net.network_address + 10), "end": str(vpn_net.network_address + 250)}
    vpn_ifs = [{"name": f"owner-vpn-{c}", "wan": w[0]} for c, w in zip("ab", WANS)]
    policies, services, shapers, shaping = expand_policies(plan, vlans, vpn_ifs)
    mgmt = next(v for v in vlans if v["name"] == "MGMT")
    mnet = netinfo(plan["vlans"][0]["subnet"])
    ctx = {
        "site": site, "fw": next(d for d in plan["devices"] if d["role"] == "firewall"),
        "mgmt": {"net": str(mnet.network_address), "mask": str(mnet.netmask), "ifname": mgmt["ifname"]},
        "wans": [{"ifname": w[0], "alias": w[1]} for w in WANS],
        "lag_members": FW_LAG, "vlans": vlans,
        "tenants": [v for v in vlans if v["name"].startswith("TENANT-")],
        "dhcp_vlans": [v for v in vlans if v["dhcp"]],
        "vpn": vpn, "vpn_ifs": vpn_ifs,
        "rfc1918": [{"name": n, "net": str(netinfo(c).network_address),
                     "mask": str(netinfo(c).netmask)} for n, c in RFC1918],
        "policies": policies, "services": services, "shapers": shapers, "shaping": shaping,
    }
    return env.get_template("fw-edge.conf.j2").render(**ctx)


def ios_common(plan, dev, site):
    mnet = netinfo(plan["vlans"][0]["subnet"])
    host = dict(dev)
    return {"site": site, "host": host,
            "mgmt": {"net": str(mnet.network_address), "wild": str(mnet.hostmask)}}


def vlan_objs(plan, ids):
    return [{"id": v["id"], "name": v["name"]} for v in plan["vlans"] if v["id"] in ids]


def sw_core(plan, env, site):
    dev = next(d for d in plan["devices"] if d["name"] == "sw-core")
    floors = plan["site"]["floors"]
    all_ids = [v["id"] for v in plan["vlans"]]
    used = set(CORE["fw"] + [CORE["mon"], CORE["admin"], CORE["nvr"], CORE["lobby_ap"]] + CORE["lobby_cctv"] + CORE["staff"]
               + [CORE["floor_base"] + n for n in range(1, floors + 1)])
    h = dev | {
        "stp_root": True, "location": "MDF rack",
        "vlans": vlan_objs(plan, all_ids),
        "fw_allowed": all_ids,
        "fw_ports": [{"ifname": gi(p), "fw_port": FW_LAG[i]} for i, p in enumerate(CORE["fw"])],
        "floor_ports": [{"ifname": gi(CORE["floor_base"] + n), "name": f"sw-f{n}",
                         "allowed": [10, 30, 40, 100 + n]} for n in range(1, floors + 1)],
        "access_ports": (
            [{"ifname": gi(CORE["mon"]), "name": "mon-01", "vlan": 10, "protected": False, "maxmac": 1},
             {"ifname": gi(CORE["admin"]), "name": "admin-port", "vlan": 10, "protected": False, "maxmac": 1},
             {"ifname": gi(CORE["nvr"]), "name": "nvr-01", "vlan": 30, "protected": False, "maxmac": 1}]
            + [{"ifname": gi(p), "name": f"cctv-lobby-{i}", "vlan": 30, "protected": True, "maxmac": 1}
               for i, p in enumerate(CORE["lobby_cctv"], 1)]
            + [{"ifname": gi(p), "name": f"staff-{i}", "vlan": 20, "protected": False, "maxmac": 3}
               for i, p in enumerate(CORE["staff"], 1)]),
        "ap_ports": [{"ifname": gi(CORE["lobby_ap"]), "name": "ap-lobby", "allowed": [10, 40]}],
        "spare_ports": [{"ifname": gi(p)} for p in range(1, PORTS + 1) if p not in used],
    }
    ctx = ios_common(plan, h, site)
    ctx["host"] = h
    return env.get_template("sw-core.cfg.j2").render(**ctx)


def sw_access(plan, dev, env, site):
    ap = plan["access_ports"]
    n = dev["floor"]
    tv = 100 + n
    aps = sorted(d["name"] for d in plan["devices"] if d["role"] == "ap" and d.get("floor") == n)
    used = set(range(1, ap["room_ports"] + 1)) | set(ap["ap_ports"]) | set(ap["cctv_ports"]) | {ap["uplink"]}
    h = dev | {
        "stp_root": False, "location": f"floor {n}",
        "tenant_vlan": tv,
        "vlans": vlan_objs(plan, [10, 30, 40, tv]),
        "snoop_vlans": [40, tv],
        "uplink_if": gi(ap["uplink"]), "core_port": CORE["floor_base"] + n,
        "uplink_allowed": [10, 30, 40, tv],
        "ap_allowed": [10, 40, tv],
        "room_ports": [{"ifname": gi(i), "room": n * 100 + i} for i in range(1, ap["room_ports"] + 1)],
        "ap_ports": [{"ifname": gi(p), "name": aps[i]} for i, p in enumerate(ap["ap_ports"])],
        "cctv_ports": [{"ifname": gi(p), "n": i} for i, p in enumerate(ap["cctv_ports"], 1)],
        "spare_ports": [{"ifname": gi(p)} for p in range(1, PORTS + 1) if p not in used],
    }
    ctx = ios_common(plan, h, site)
    return env.get_template("sw-access.cfg.j2").render(**ctx)


def clean(text):
    return "\n".join(l.rstrip() for l in text.splitlines()) + "\n"


def inventory(plan):
    def host(d):
        return {"ansible_host": d["mgmt_ip"]}
    devs = {d["name"]: d for d in plan["devices"]}
    inv = {"all": {"children": {
        "fortigate": {"hosts": {"fw-edge": host(devs["fw-edge"])},
                      "vars": {"ansible_network_os": "fortinet.fortios.fortios"}},
        "cisco_core": {"hosts": {"sw-core": host(devs["sw-core"])}},
        "cisco_access": {"hosts": {n: host(d) for n, d in devs.items() if d["role"] == "access-switch"}},
        "cisco": {"children": {"cisco_core": None, "cisco_access": None},
                  "vars": {"ansible_network_os": "cisco.ios.ios", "ansible_connection": "ansible.netcommon.network_cli"}},
    }}}
    return yaml.safe_dump(inv, sort_keys=False)


def main():
    plan = load()
    env = Environment(loader=FileSystemLoader(HERE / "templates"), undefined=StrictUndefined,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    site = dict(EXTRA) | {"name": plan["site"]["name"], "room_ports": plan["access_ports"]["room_ports"],
                          "mgmt_gw": plan["vlans"][0]["gw"], "ntp_server": plan["vlans"][0]["gw"]}
    (OUT / "fortigate").mkdir(parents=True, exist_ok=True)
    (OUT / "cisco").mkdir(parents=True, exist_ok=True)
    files = {OUT / "fortigate" / "fw-edge.conf": fortigate(plan, env, site),
             OUT / "cisco" / "sw-core.cfg": sw_core(plan, env, site)}
    for d in plan["devices"]:
        if d["role"] == "access-switch":
            files[OUT / "cisco" / f"{d['name']}.cfg"] = sw_access(plan, d, env, site)
    files[HERE / "ansible" / "inventory" / "hosts.yml"] = inventory(plan)
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(clean(text))
        print("wrote", path.relative_to(HERE))


if __name__ == "__main__":
    main()
