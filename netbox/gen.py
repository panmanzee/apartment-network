#!/usr/bin/env python3
"""Read plan/ip-plan.yaml, write NetBox import files and generated docs.
Run from anywhere: python3 netbox/gen.py   (safe to re-run, output is deterministic)
Simulated client, nothing here is a real site.
"""
import csv
import ipaddress
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "plan" / "ip-plan.yaml"
OUT = ROOT / "netbox" / "import"
DOCS = ROOT / "docs"

# Things the yaml does not say. They live here and in the docs, not in the yaml.
TRANSIT_VID = 999
TRANSIT_NAME = "TRANSIT"
DHCP_FIRST, DHCP_LAST = 100, 250
LEASE = {"GUEST": "2 hours"}
LEASE_DEFAULT = "1 day"
GUEST_DNS = "1.1.1.1, 1.0.0.1"
STAFF_RESERVATIONS = [("printer-01", 20), ("pos-01", 21)]
MON = {"name": "mon-01", "role": "monitoring", "mgmt_ip": "10.20.10.50"}
CAM_BASE = 100  # cam n -> 10.20.30.(100+n)
CORE_CAMS = ["gate", "parking", "lobby", "back"]
SW_MODEL = {"core-switch": "Core Switch 24p", "access-switch": "Access Switch 24p"}
MODELS = [
    ("Fortinet", "Edge Firewall", "firewall"),
    ("TP-Link", "Core Switch 24p", "core-switch"),
    ("TP-Link", "Access Switch 24p", "access-switch"),
    ("TP-Link", "Omada AP", "ap"),
    ("Generic", "NVR", "nvr"),
    ("Generic", "IP Camera", "camera"),
    ("Generic", "Monitoring Server", "monitoring"),
]
ROLE_COLOR = {"firewall": "f44336", "core-switch": "2196f3", "access-switch": "03a9f4",
              "ap": "4caf50", "nvr": "9c27b0", "camera": "795548", "monitoring": "ff9800"}


def load():
    return yaml.safe_load(PLAN.read_text())


def floor_vlan(plan, n):
    return next(v for v in plan["vlans"] if v["name"] == f"TENANT-F{n}")


def build(plan):
    site = plan["site"]
    ap = plan["access_ports"]
    vname = {v["id"]: v["name"] for v in plan["vlans"]}
    m = {"site": site["name"], "slug": site["slug"], "plan": plan}
    vlans = [{"vid": v["id"], "name": v["name"], "desc": v["desc"]} for v in plan["vlans"]]
    vlans.append({"vid": TRANSIT_VID, "name": TRANSIT_NAME,
                  "desc": "native VLAN on the fw-edge to sw-core trunk, carries the transit /30 only"})
    m["vlans"] = vlans

    prefixes = [{"prefix": v["subnet"], "vid": v["id"], "desc": f"{v['name']}: {v['desc']}"}
                for v in plan["vlans"]]
    prefixes.append({"prefix": plan["transit"]["core_fw"], "vid": TRANSIT_VID,
                     "desc": "transit fw-edge .1 / sw-core .2"})
    prefixes.append({"prefix": plan["vpn"]["owner"]["pool"], "vid": None,
                     "desc": "owner remote access VPN pool"})
    m["prefixes"] = prefixes

    devices = [dict(d) for d in plan["devices"]]
    devices.append(dict(MON))
    cams = []
    n = 0
    for f in range(1, 6):
        for p in plan["access_ports"]["cctv_ports"]:
            n += 1
            cams.append({"name": f"cam-f{f}-{p - 14}", "role": "camera", "floor": f,
                         "sw": f"sw-f{f}", "port": p, "mgmt_ip": f"10.20.30.{CAM_BASE + n}"})
    for i, loc in enumerate(CORE_CAMS, 1):
        n += 1
        cams.append({"name": f"cam-core-{i}", "role": "camera", "floor": 0, "sw": "sw-core",
                     "port": 8 + i, "mgmt_ip": f"10.20.30.{CAM_BASE + n}", "loc": loc})
    m["cams"] = cams
    devices += [{k: c[k] for k in ("name", "role", "mgmt_ip", "floor")} for c in cams]
    m["devices"] = devices

    # port maps: {device: [(port, kind, untagged, tagged, peer/desc, protected)]}
    ports = {}
    core = []
    core.append(("Gi1/0/1", "trunk to fw-edge", TRANSIT_VID, "10,20,30,40,101-105", "fw-edge lan1", False))
    for f in range(1, 6):
        core.append((f"Gi1/0/{f + 1}", f"uplink sw-f{f}", 10, f"30,{100 + f}", f"sw-f{f} Gi1/0/{ap['uplink']}", False))
    core.append(("Gi1/0/7", "nvr-01", 30, "", "nvr-01", False))
    core.append(("Gi1/0/8", "ap-lobby", 10, "40", "ap-lobby", True))
    for i, loc in enumerate(CORE_CAMS, 1):
        core.append((f"Gi1/0/{8 + i}", f"cam-core-{i} ({loc})", 30, "", f"cam-core-{i}", True))
    core.append(("Gi1/0/13", "mon-01", 10, "", "mon-01", False))
    for p in range(14, 19):
        core.append((f"Gi1/0/{p}", "staff office", 20, "", "office PC / printer / POS", False))
    core.append((f"Gi1/0/{ap['uplink']}", "admin laptop (MGMT)", 10, "", "admin port", False))
    ports["sw-core"] = core
    for f in range(1, 6):
        rows = []
        tv = 100 + f
        for r in range(1, ap["room_ports"] + 1):
            rows.append((f"Gi1/0/{r}", f"room {f}{r:02d}", tv, "", f"room {f}{r:02d} wall jack", True))
        for i, p in enumerate(ap["ap_ports"]):
            nm = f"ap-f{f}-{'ab'[i]}"
            rows.append((f"Gi1/0/{p}", nm, 10, str(tv), nm, True))
        for i, p in enumerate(ap["cctv_ports"], 1):
            rows.append((f"Gi1/0/{p}", f"cam-f{f}-{i}", 30, "", f"cam-f{f}-{i}", True))
        rows.append((f"Gi1/0/{ap['uplink']}", "uplink to sw-core", 10, f"30,{tv}", f"sw-core Gi1/0/{f + 1}", False))
        ports[f"sw-f{f}"] = rows
    m["ports"] = ports

    # IPs
    ips = []
    gw_if = {v["name"]: v for v in plan["vlans"]}
    for v in plan["vlans"]:
        ips.append({"address": f"{v['gw']}/24", "device": "fw-edge", "iface": f"vlan{v['id']}",
                    "dns": "", "status": "active", "desc": f"gateway {v['name']}", "primary": v["id"] == 10})
    ips.append({"address": "10.20.0.1/30", "device": "fw-edge", "iface": "lan1", "dns": "",
                "status": "active", "desc": "transit", "primary": False})
    ips.append({"address": "10.20.0.2/30", "device": "sw-core", "iface": "Gi1/0/1", "dns": "",
                "status": "active", "desc": "transit", "primary": False})
    for d in devices:
        if d["name"] == "fw-edge":
            continue
        net = "10.20.30" if d["role"] in ("nvr", "camera") else "10.20.10"
        ifn = "eth0" if d["role"] in ("nvr", "camera", "monitoring", "ap") else "vlan10"
        ips.append({"address": f"{d['mgmt_ip']}/24", "device": d["name"], "iface": ifn,
                    "dns": f"{d['name']}.baan-chalong.lan", "status": "active",
                    "desc": "management" if net == "10.20.10" else "CCTV VLAN", "primary": True})
    for nm, last in STAFF_RESERVATIONS:
        ips.append({"address": f"10.20.20.{last}/24", "device": "", "iface": "", "dns": f"{nm}.baan-chalong.lan",
                    "status": "reserved", "desc": f"DHCP reservation {nm}", "primary": False})
    m["ips"] = ips

    # interfaces for NetBox
    ifs = []
    ifs.append({"device": "fw-edge", "name": "wan1", "type": "1000base-t", "mode": "", "desc": plan["site"]["isp"]["primary"]["name"]})
    ifs.append({"device": "fw-edge", "name": "wan2", "type": "1000base-t", "mode": "", "desc": plan["site"]["isp"]["backup"]["name"]})
    ifs.append({"device": "fw-edge", "name": "lan1", "type": "1000base-t", "mode": "tagged", "desc": "trunk to sw-core Gi1/0/1; untagged 999; tagged 10,20,30,40,101-105",
                "untagged": TRANSIT_VID, "tagged": "10,20,30,40,101-105"})
    for v in plan["vlans"]:
        ifs.append({"device": "fw-edge", "name": f"vlan{v['id']}", "type": "virtual", "mode": "", "desc": f"gateway {v['name']}"})
    for sw in ["sw-core"] + [f"sw-f{f}" for f in range(1, 6)]:
        ifs.append({"device": sw, "name": "vlan10", "type": "virtual", "mode": "", "desc": "management"})
    for dev, rows in ports.items():
        for port, what, un, tg, peer, prot in rows:
            ifs.append({"device": dev, "name": port, "type": "1000base-t",
                        "mode": "tagged" if tg else "access",
                        "desc": f"{what}; untagged {un}" + (f"; tagged {tg}" if tg else "") + ("; protected" if prot else ""),
                        "untagged": un, "tagged": tg})
    for d in devices:
        if d["role"] in ("ap", "nvr", "camera", "monitoring"):
            ifs.append({"device": d["name"], "name": "eth0", "type": "1000base-t", "mode": "", "desc": "uplink"})
    m["ifaces"] = ifs
    return m


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def emit_csv(m):
    OUT.mkdir(parents=True, exist_ok=True)
    site = m["site"]
    write_csv(OUT / "sites.csv", ["name", "slug", "status", "description"],
              [[site, m["slug"], "active", "SIMULATED client, fictional 5-floor apartment near KMITL Lat Krabang"]])
    mans = sorted({a for a, _, _ in MODELS})
    write_csv(OUT / "manufacturers.csv", ["name", "slug"], [[x, x.lower()] for x in mans])
    write_csv(OUT / "device-roles.csv", ["name", "slug", "color"],
              [[r, r, ROLE_COLOR[r]] for _, _, r in MODELS])
    write_csv(OUT / "device-types.csv", ["manufacturer", "model", "slug"],
              [[a, b, b.lower().replace(" ", "-")] for a, b, _ in MODELS])
    write_csv(OUT / "vlans.csv", ["site", "vid", "name", "status", "description"],
              [[site, v["vid"], v["name"], "active", v["desc"]] for v in m["vlans"]])
    write_csv(OUT / "prefixes.csv", ["prefix", "status", "scope_type", "scope", "vlan_site", "vlan", "description"],
              [[p["prefix"], "active", "dcim.site", site, site if p["vid"] else "",
                next((v["name"] for v in m["vlans"] if v["vid"] == p["vid"]), ""), p["desc"]]
               for p in m["prefixes"]])
    model_of = {r: b for _, b, r in MODELS}
    man_of = {r: a for a, _, r in MODELS}
    write_csv(OUT / "devices.csv", ["name", "role", "manufacturer", "device_type", "status", "site", "description"],
              [[d["name"], d["role"], man_of[d["role"]], model_of[d["role"]], "active", site,
                f"floor {d['floor']}" if "floor" in d else ""] for d in m["devices"]])
    write_csv(OUT / "interfaces.csv", ["device", "name", "type", "enabled", "mode", "description"],
              [[i["device"], i["name"], i["type"], "true", i["mode"], i["desc"]] for i in m["ifaces"]])
    write_csv(OUT / "ip-addresses.csv",
              ["address", "status", "dns_name", "description", "device", "interface", "is_primary"],
              [[i["address"], i["status"], i["dns"], i["desc"], i["device"], i["iface"],
                "true" if i["primary"] and i["device"] else "false"] for i in m["ips"]])


def emit_yaml(m):
    data = {
        "simulated": True,
        "site": {"name": m["site"], "slug": m["slug"]},
        "manufacturers": sorted({a for a, _, _ in MODELS}),
        "device_roles": [r for _, _, r in MODELS],
        "device_types": [{"manufacturer": a, "model": b, "role": r} for a, b, r in MODELS],
        "vlans": m["vlans"],
        "prefixes": m["prefixes"],
        "devices": m["devices"],
        "interfaces": m["ifaces"],
        "ip_addresses": m["ips"],
    }
    (OUT / "netbox.yaml").write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False, width=200))


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) if str(c) != "" else "-" for c in r) + " |")
    return "\n".join(out)


def dhcp_rows(plan):
    rows = []
    for v in plan["vlans"]:
        net = ipaddress.ip_network(v["subnet"])
        base = str(net.network_address).rsplit(".", 1)[0]
        if v["dhcp"]:
            dns = GUEST_DNS if v["name"] == "GUEST" else f"{v['gw']} (fw forwarder)"
            rows.append([v["id"], v["name"], v["subnet"], v["gw"], f"{base}.{DHCP_FIRST}-{base}.{DHCP_LAST}",
                         f"{base}.2-{base}.99 static", dns, LEASE.get(v["name"], LEASE_DEFAULT)])
        else:
            rows.append([v["id"], v["name"], v["subnet"], v["gw"], "no DHCP", f"{base}.2-{base}.254 static", "-", "-"])
    return rows


def policy_rows(plan):
    p = plan["policy"]
    order = [8, 6, 7, 9, 5, 4, 3, 2, 1, 0]
    rows = []
    for n, i in enumerate(order, 1):
        r = p[i]
        dst = ", ".join(r["dst"]) if isinstance(r["dst"], list) else r["dst"]
        extra = []
        if "ports" in r:
            extra.append("tcp " + ",".join(map(str, r["ports"])))
        if "shape" in r:
            extra.append("shaper " + r["shape"])
        if "note" in r:
            extra.append(r["note"])
        nat = "SNAT to WAN" if r["dst"] == "internet" and r["action"] == "allow" else "none"
        rows.append([f"FW-{n:02d}", r["src"], dst, r["action"], "; ".join(extra) or "-", nat, "log" if r["action"] == "deny" else "off"])
    rows.append([f"FW-{len(order) + 1:02d}", "any", "any", "deny", "implicit default", "none", "log"])
    return rows


def ssid_rows(plan):
    rows = []
    for f in range(1, 6):
        v = floor_vlan(plan, f)
        rows.append([f"BCR-F{f}", v["id"], v["name"], f"ap-f{f}-a, ap-f{f}-b", "WPA2/WPA3 personal, one PSK per floor", "on", "100/50 Mbps per client"])
    g = next(v for v in plan["vlans"] if v["name"] == "GUEST")
    rows.append(["BCR-Guest", g["id"], "GUEST", "ap-lobby", "open + captive portal (voucher)", "on", "20/10 Mbps per client"])
    return rows


def emit_docs(m):
    plan = m["plan"]
    gen_note = "<!-- generated by netbox/gen.py from plan/ip-plan.yaml, do not edit by hand -->"
    sim = "> SIMULATED PROJECT. Baan Chalong Residence is a made-up client. Nothing here is a real site."

    # ip-plan.md
    L = [gen_note, "# IP plan", "", sim, "",
         "Source: `plan/ip-plan.yaml`. Rows marked (doc) are not in the yaml, they are choices made in the docs.", "",
         "## VLANs and subnets", "",
         md_table(["VLAN", "Name", "Subnet", "Gateway (on fw-edge)", "DHCP", "Use"],
                  [[v["id"], v["name"], v["subnet"], v["gw"], "yes" if v["dhcp"] else "no", v["desc"]] for v in plan["vlans"]]
                  + [[TRANSIT_VID, TRANSIT_NAME + " (doc)", plan["transit"]["core_fw"], "fw .1 / core .2", "no", "transit, native VLAN on trunk"]]),
         "", "## Other prefixes", "",
         md_table(["Prefix", "Use"], [[plan["vpn"]["owner"]["pool"], "owner VPN pool, allowed: " + ", ".join(plan["vpn"]["owner"]["allowed"])]]),
         "", "## DHCP scopes", "",
         md_table(["VLAN", "Name", "Subnet", "Gateway", "Pool (doc)", "Static range (doc)", "DNS", "Lease (doc)"], dhcp_rows(plan)),
         "", "## Device addresses", "",
         md_table(["Device", "Role", "IP", "Floor"],
                  [[d["name"], d["role"], d["mgmt_ip"], d.get("floor", "-")] for d in m["devices"] if d["role"] != "camera"]),
         "", "mon-01 is added in the docs, it is not in the yaml.", "",
         "## Cameras (doc)", "",
         "24 cameras: 4 per floor on the floor switch, 4 on sw-core (gate, parking, lobby, back). NVR is nvr-01 10.20.30.10.", "",
         md_table(["Camera", "IP", "Switch", "Port"], [[c["name"], c["mgmt_ip"], c["sw"], f"Gi1/0/{c['port']}"] for c in m["cams"]]),
         "", "## Reservations (doc)", "",
         md_table(["Name", "IP", "VLAN"], [[n, f"10.20.20.{l}", "STAFF"] for n, l in STAFF_RESERVATIONS]), ""]
    (DOCS / "ip-plan.md").write_text("\n".join(L))

    # lld.md
    ap = plan["access_ports"]
    T = [gen_note, "# Low-level design", "", sim, "",
         "All tables here come from `plan/ip-plan.yaml` through `netbox/gen.py`. Change the yaml, run the script, do not edit this file.",
         "Design decision: sw-core is a layer-2 switch. All VLAN gateways are on fw-edge (see hld.md).", "",
         "## 1. Naming", "",
         "- Devices: `role-site`: `fw-edge`, `sw-core`, `sw-f<floor>`, `ap-f<floor>-a|b`, `ap-lobby`, `nvr-01`, `cam-f<floor>-<n>`, `cam-core-<n>`, `mon-01`.",
         "- Rooms: floor digit + two digits, room 305 is on floor 3, port Gi1/0/5 of sw-f3.",
         "- SSIDs: `BCR-F1` to `BCR-F5`, `BCR-Guest`.",
         "- DNS names: `<device>.baan-chalong.lan`.",
         "- Firewall rules: `FW-nn`, in the order of the table in section 6.", "",
         "## 2. VLAN table", "",
         md_table(["VLAN", "Name", "Subnet", "Gateway", "Use"],
                  [[v["id"], v["name"], v["subnet"], v["gw"], v["desc"]] for v in plan["vlans"]]
                  + [[TRANSIT_VID, TRANSIT_NAME + " (doc)", plan["transit"]["core_fw"], "-", "native VLAN of the fw-edge to sw-core trunk"]]),
         "", "## 3. DHCP scopes", "",
         md_table(["VLAN", "Name", "Subnet", "Gateway", "Pool", "Static", "DNS", "Lease"], dhcp_rows(plan)),
         "", "Reservations: " + ", ".join(f"{n} 10.20.20.{l}" for n, l in STAFF_RESERVATIONS) + ".",
         "Switches, APs, NVR, cameras and mon-01 use static addresses (see ip-plan.md).", "",
         "## 4. Port maps", "",
         f"Rule: room NNN is port Gi1/0/(NNN%100) on sw-fN, untagged TENANT-FN, protected. Ports 1-{ap['room_ports']} rooms, "
         f"{ap['ap_ports'][0]}-{ap['ap_ports'][-1]} APs, {ap['cctv_ports'][0]}-{ap['cctv_ports'][-1]} cameras, {ap['uplink']} uplink.",
         "Protected = no traffic to other protected ports on the same switch. Only the uplink is not protected.", ""]
    for dev in ["sw-core"] + [f"sw-f{f}" for f in range(1, 6)]:
        ip = next(d["mgmt_ip"] for d in m["devices"] if d["name"] == dev)
        T += [f"### {dev} ({ip})", "",
              md_table(["Port", "Connected", "Untagged VLAN", "Tagged VLANs", "Peer", "Protected"],
                       [[p, w, u, t, pe, "yes" if pr else "no"] for p, w, u, t, pe, pr in m["ports"][dev]]), ""]
    T += ["Unused ports: shut down, description `unused`. Ports 19-23 on sw-fN are spare.", "",
          "## 5. Wi-Fi (Omada)", "",
          md_table(["SSID", "VLAN", "Zone", "APs", "Security", "Client isolation", "Rate limit"], ssid_rows(plan)),
          "", "AP management is on MGMT 10 (untagged on the AP port). Each AP port carries its own floor VLAN tagged. ap-lobby carries VLAN 40.", "",
          "## 6. Firewall policy (fw-edge, top to bottom, first match wins)", "",
          md_table(["Rule", "Source", "Destination", "Action", "Detail", "NAT", "Log"], policy_rows(plan)),
          "", "- `internet` = anything outside RFC1918. `rfc1918` = 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16.",
          "- GUEST deny to rfc1918 sits above GUEST allow to internet on purpose.",
          "- Local-in (traffic to the firewall itself): DHCP and DNS from every VLAN except CCTV, NTP from CCTV, SSH/HTTPS admin only from MGMT and OWNER-VPN.",
          "- Shapers are per-IP on the firewall (tenant 100/50, guest 20/10). Wired rooms also get a 100/50 limit on the switch port.",
          "- NAT: source NAT to the active WAN interface for every internet allow rule. No NAT for VPN traffic.", "",
          "## 7. WAN and VPN", "",
          f"- wan1: {plan['site']['isp']['primary']['name']}, {plan['site']['isp']['primary']['wan']}. wan2: {plan['site']['isp']['backup']['name']}, {plan['site']['isp']['backup']['wan']}.",
          "- wan1 is primary, wan2 takes over when the health check to two public hosts fails. No load sharing.",
          f"- Owner VPN: {plan['vpn']['owner']['type']}, pool {plan['vpn']['owner']['pool']}, allowed: {', '.join(plan['vpn']['owner']['allowed'])}. Chosen for the build: IPsec IKEv2 on fw-edge, split tunnel.", ""]
    (DOCS / "lld.md").write_text("\n".join(T))


def main():
    m = build(load())
    emit_csv(m)
    emit_yaml(m)
    emit_docs(m)
    print(f"ok: {len(m['vlans'])} vlans, {len(m['devices'])} devices, {len(m['ifaces'])} interfaces, {len(m['ips'])} ips")


if __name__ == "__main__":
    main()
