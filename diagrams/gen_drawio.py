#!/usr/bin/env python3
"""Draw the physical and logical diagrams (draw.io) from plan/ip-plan.yaml."""
from html import escape
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
PLAN = yaml.safe_load((HERE.parent / "plan" / "ip-plan.yaml").read_text())

BOX = "rounded=1;whiteSpace=wrap;html=1;arcSize=6;"
COL = {
    "blue": "fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "green": "fillColor=#d5e8d4;strokeColor=#82b366;",
    "orange": "fillColor=#ffe6cc;strokeColor=#d79b00;",
    "purple": "fillColor=#e1d5e7;strokeColor=#9673a6;",
    "grey": "fillColor=#f5f5f5;strokeColor=#666666;",
    "yellow": "fillColor=#fff2cc;strokeColor=#d6b656;",
    "red": "fillColor=#f8cecc;strokeColor=#b85450;",
    "white": "fillColor=#ffffff;strokeColor=#999999;",
}


class Doc:
    def __init__(self, name, w, h):
        self.name, self.w, self.h = name, w, h
        self.cells = []
        self.n = 1

    def _id(self):
        self.n += 1
        return f"c{self.n}"

    def box(self, x, y, w, h, label, color="white", extra="", cid=None):
        cid = cid or self._id()
        style = BOX + COL[color] + extra
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label, quote=True)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def cloud(self, x, y, w, h, label, cid=None):
        cid = cid or self._id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label, quote=True)}" style="ellipse;shape=cloud;whiteSpace=wrap;html=1;'
            f'fillColor=#f5f5f5;strokeColor=#666666;" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def text(self, x, y, w, h, label, size=12, align="left"):
        cid = self._id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label, quote=True)}" style="text;html=1;whiteSpace=wrap;align={align};'
            f'verticalAlign=top;fontSize={size};" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def edge(self, a, b, label="", color="#333333", dashed=False, points=None, exit_xy=None, entry_xy=None, width=1):
        cid = self._id()
        st = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor={color};strokeWidth={width};"
              f"endArrow=none;fontSize=10;")
        if dashed:
            st += "dashed=1;"
        if exit_xy:
            st += f"exitX={exit_xy[0]};exitY={exit_xy[1]};exitDx=0;exitDy=0;"
        if entry_xy:
            st += f"entryX={entry_xy[0]};entryY={entry_xy[1]};entryDx=0;entryDy=0;"
        pts = ""
        if points:
            pts = "<Array as=\"points\">" + "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in points) + "</Array>"
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label, quote=True)}" style="{st}" edge="1" parent="1" source="{a}" target="{b}">'
            f'<mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>')
        return cid

    def save(self, path):
        xml = (f'<mxfile host="gen_drawio.py"><diagram name="{self.name}" id="{self.name}">'
               f'<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
               f'fold="1" page="1" pageScale="1" pageWidth="{self.w}" pageHeight="{self.h}" math="0" shadow="0">'
               f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(self.cells) +
               '</root></mxGraphModel></diagram></mxfile>\n')
        Path(path).write_text(xml)


def devs(role):
    return [d for d in PLAN["devices"] if d["role"] == role]


def dev(name):
    return next(d for d in PLAN["devices"] if d["name"] == name)


def vlan_legend():
    rows = "".join(
        f"<tr><td>{v['id']}</td><td>{v['name']}</td><td>{v['subnet']}</td><td>{'dhcp' if v['dhcp'] else 'static'}</td></tr>"
        for v in PLAN["vlans"])
    return ("<b>VLANs</b><table border='1' cellpadding='3' style='border-collapse:collapse;font-size:11px'>"
            "<tr><th>id</th><th>name</th><th>subnet</th><th>addr</th></tr>" + rows + "</table>"
            f"<br><b>Owner VPN pool</b> {PLAN['vpn']['owner']['pool']}<br>"
            f"<b>Transit</b> {PLAN['transit']['core_fw']} (reserved, fw routes on lag-core subinterfaces)")


def physical():
    ap = PLAN["access_ports"]
    site = PLAN["site"]
    floors = site["floors"]
    d = Doc("physical", 1700, 1160)
    d.text(40, 10, 1200, 30, f"<b>{site['name']}</b> - physical topology, {floors} floors, {site['rooms']} rooms (simulated)", 18)
    d.box(40, 60, 420, 330, vlan_legend(), "white", "align=left;verticalAlign=top;spacing=6;")

    fh, gap, fx, fw_ = 150, 15, 520, 1120
    ytop = 60
    floor_y = {n: ytop + (floors - n) * (fh + gap) for n in range(1, floors + 1)}
    lobby_y = ytop + floors * (fh + gap)
    chan_x = {n: 475 + 9 * n for n in range(1, floors + 1)}

    # rack
    d.cloud(60, 560, 170, 90, "ISP-A<br>" + PLAN["site"]["isp"]["primary"]["name"].replace("ISP-A ", ""), "isp_a")
    d.cloud(270, 560, 170, 90, "ISP-B<br>" + PLAN["site"]["isp"]["backup"]["name"].replace("ISP-B ", ""), "isp_b")
    ry = lobby_y - 205
    d.box(40, ry, 420, 430, "<b>MDF rack (ground floor)</b>", "yellow", "verticalAlign=bottom;align=left;spacingLeft=8;fillOpacity=40;")
    d.box(110, ry + 55, 280, 80, f"<b>fw-edge</b> FortiGate 60F<br>{dev('fw-edge')['mgmt_ip']}<br>wan1 / wan2 (SD-WAN), lag-core = internal1+2", "red", cid="fw")
    d.box(110, ry + 270, 280, 80, f"<b>sw-core</b> Catalyst 24p, STP root<br>{dev('sw-core')['mgmt_ip']}", "blue", cid="core")
    d.edge("isp_a", "fw", "wan1 (DHCP)", exit_xy=(0.5, 1), entry_xy=(0.25, 0), color="#b85450", width=2)
    d.edge("isp_b", "fw", "wan2 (DHCP, backup)", exit_xy=(0.5, 1), entry_xy=(0.75, 0), color="#b85450", width=2)
    d.edge("fw", "core", "LACP Po1: internal1-2 / Gi1/0/1-2, trunk all VLANs", exit_xy=(0.5, 1), entry_xy=(0.5, 0), width=3)

    # floors
    for n in range(1, floors + 1):
        y = floor_y[n]
        tv = 100 + n
        d.box(fx, y, fw_, fh, f"<b>Floor {n}</b>", "grey", "verticalAlign=top;align=left;spacingLeft=8;fillOpacity=30;")
        sid = f"swf{n}"
        d.box(fx + 30, y + 45, 160, 70, f"<b>sw-f{n}</b><br>{dev(f'sw-f{n}')['mgmt_ip']}<br>uplink Gi1/0/{ap['uplink']} -> core Gi1/0/{10 + n}", "blue", cid=sid)
        aps = sorted(x["name"] for x in devs("ap") if x.get("floor") == n)
        d.box(fx + 240, y + 22, 310, 60, "", "white", "dashed=1;fillColor=none;", cid=f"apg{n}")
        d.box(fx + 240, y + 88, 610, 50, "", "white", "dashed=1;fillColor=none;", cid=f"camg{n}")
        for i, (name, port) in enumerate(zip(aps, ap["ap_ports"])):
            cid = f"ap{n}{i}"
            d.box(fx + 250 + i * 150, y + 30, 135, 45, f"{name}<br>Gi1/0/{port} trunk", "green", cid=cid)
        for i, port in enumerate(ap["cctv_ports"]):
            cid = f"cam{n}{i}"
            d.box(fx + 250 + i * 150, y + 92, 135, 40, f"cctv-f{n}-{i + 1}<br>Gi1/0/{port}", "orange", cid=cid)
        d.edge(sid, f"apg{n}", exit_xy=(1, 0.3), entry_xy=(0, 0.5))
        d.edge(sid, f"camg{n}", exit_xy=(1, 0.75), entry_xy=(0, 0.5))
        rid = f"rooms{n}"
        d.box(fx + 880, y + 28, 225, 102,
              f"<b>{ap['room_ports']} rooms {n}01-{n}{ap['room_ports']:02d}</b><br>Gi1/0/1-{ap['room_ports']}, VLAN {tv}<br>"
              f"10.21.{n}.0/24<br>protected, port-sec, bpduguard", "white", cid=rid)
        d.edge("swf%d" % n, rid, "", exit_xy=(0.5, 1), entry_xy=(0.5, 1), points=[(fx + 110, y + 143), (fx + 992, y + 143)])
        cx = chan_x[n]
        d.edge("core", sid, "", exit_xy=(1, 0.5), entry_xy=(0, 0.5),
               points=[(cx, ry + 310), (cx, y + 80)], color="#6c8ebf", width=2)

    # lobby
    d.box(fx, lobby_y, fw_, 225, "<b>Lobby / ground floor</b>", "grey", "verticalAlign=top;align=left;spacingLeft=8;fillOpacity=30;")
    items = [("aplobby", "ap-lobby (10.20.10.41), Gi1/0/6 trunk native 10, allowed 10,40", "green"),
             ("nvr", "nvr-01 (10.20.30.10), Gi1/0/5 access VLAN 30", "orange"),
             ("cl", "4 lobby cameras, Gi1/0/7-10 access VLAN 30", "orange"),
             ("staff", "staff office: Gi1/0/17-20 access VLAN 20 (PCs, printer, POS)", "green")]
    for i, (cid, label, col) in enumerate(items):
        d.box(fx + 200, lobby_y + 35 + i * 46, 520, 38, label, col, cid=cid)
        d.edge("core", cid, exit_xy=(1, 0.5), entry_xy=(0, 0.5))

    d.text(40, 1120, 1600, 30, "24 cameras: 4 per floor x 5 + 4 in lobby. Room ports are 'switchport protected' so rooms cannot reach each other at L2.", 11)
    d.save(HERE / "physical.drawio")


def rule_text(src_names):
    out = []
    for r in PLAN["policy"]:
        if r["src"] in src_names:
            dst = r["dst"] if isinstance(r["dst"], str) else "+".join(r["dst"])
            extra = ""
            if "shape" in r:
                extra += f" {r['shape']}"
            if "ports" in r:
                extra += " tcp " + "/".join(map(str, r["ports"]))
            if "note" in r:
                extra += f" ({r['note']})"
            out.append(f"-> {dst}: <b>{r['action']}</b>{extra}")
    return out


def logical():
    site = PLAN["site"]
    d = Doc("logical", 1700, 1250)
    d.text(40, 10, 1200, 30, f"<b>{site['name']}</b> - logical topology: VLANs, zones, firewall policy, VPN", 18)
    d.cloud(40, 120, 230, 110, "Internet<br>(ISP-A and ISP-B)", "net")
    d.box(40, 290, 230, 60, "ISP-A FTTx 1000/500<br>wan1 (preferred)", "grey", cid="ia")
    d.box(40, 370, 230, 60, "ISP-B FTTx 500/500<br>wan2 (failover)", "grey", cid="ib")
    d.edge("net", "ia", exit_xy=(0.5, 1), entry_xy=(0.5, 0))
    d.box(40, 560, 230, 90, "Owner laptop<br>FortiClient IPsec (IKEv2)<br>pool " + PLAN["vpn"]["owner"]["pool"], "yellow", cid="vpn")
    d.edge("net", "vpn", "dial-up", exit_xy=(0, 0.5), entry_xy=(0, 0.5), dashed=True, points=[(15, 175), (15, 605)])

    d.box(360, 100, 360, 560, "<b>fw-edge</b> FortiGate 60F (10.20.10.1)", "red", "verticalAlign=top;fillOpacity=40;", cid="fw")
    d.box(380, 150, 320, 70, "SD-WAN zone virtual-wan-link<br>wan1 + wan2, ping health-check, failover", "white", cid="sdw")
    d.box(380, 235, 320, 70, "NAT (outgoing iface) + per-IP shapers<br>tenant 100/50 Mbps, guest 20/10 Mbps", "white")
    d.box(380, 320, 320, 80, "IPsec dial-up owner-vpn-a / -b<br>pool " + PLAN["vpn"]["owner"]["pool"] + "<br>allowed: " + ", ".join(PLAN["vpn"]["owner"]["allowed"]), "white", cid="ipsec")
    d.box(380, 415, 320, 70, "DHCP server per VLAN, captive portal on GUEST<br>SNMPv3, admin only from MGMT", "white")
    d.box(380, 500, 320, 140, "<b>lag-core</b> (internal1 + internal2, LACP)<br>VLAN subinterfaces, gateway of every subnet<br>inter-VLAN traffic is filtered here", "blue", cid="lag")
    d.edge("ia", "sdw", "wan1", exit_xy=(1, 0.5), entry_xy=(0, 0.3), color="#b85450", width=2, points=[(310, 320), (310, 171)])
    d.edge("ib", "sdw", "wan2", exit_xy=(1, 0.5), entry_xy=(0, 0.7), color="#b85450", width=2, points=[(330, 400), (330, 199)])
    d.edge("vpn", "ipsec", "", exit_xy=(1, 0.5), entry_xy=(0, 0.5), dashed=True, points=[(330, 605), (330, 360)])

    d.box(820, 520, 150, 120, "<b>sw-core</b><br>L2 only<br>10.20.10.2<br>Po1 trunk to fw", "blue", cid="core")
    d.edge("lag", "core", "trunk, all VLANs", exit_xy=(1, 0.5), entry_xy=(0, 0.5), width=3)

    colors = {"MGMT": "blue", "STAFF": "green", "CCTV": "orange", "GUEST": "purple"}
    bx, bw, bh, gap = 1080, 560, 100, 12
    y = 60
    for v in PLAN["vlans"]:
        name = v["name"]
        src = {name, "TENANT-*"} if name.startswith("TENANT-") else {name}
        if name.startswith("TENANT-"):
            src = {"TENANT-*"}
        lines = rule_text(src)
        head = (f"<b>VLAN {v['id']} {name}</b> {v['subnet']} gw {v['gw']} {'dhcp' if v['dhcp'] else 'static'}<br>"
                f"<font style='font-size:10px'>{v['desc']}</font><br>")
        body = "<font style='font-size:10px'>" + "<br>".join(lines) + "</font>"
        h = 62 + 13 * len(lines)
        cid = f"v{v['id']}"
        d.box(bx, y, bw, h, head + body, colors.get(name, "grey"), "align=left;verticalAlign=top;spacingLeft=6;", cid=cid)
        d.edge("core", cid, exit_xy=(1, 0.5), entry_xy=(0, 0.5), points=[(1025 + (v["id"] % 7) * 2, 580), (1025 + (v["id"] % 7) * 2, y + h // 2)])
        y += h + gap
    vpn_rules = rule_text({"OWNER-VPN"})
    d.box(360, 700, 600, 40 + 15 * len(vpn_rules), "<b>OWNER-VPN</b> " + PLAN["vpn"]["owner"]["pool"] + "<br>" + "<br>".join(vpn_rules), "yellow", "align=left;verticalAlign=top;spacingLeft=6;")

    rows = ""
    for i, r in enumerate(PLAN["policy"], 1):
        dst = r["dst"] if isinstance(r["dst"], str) else ", ".join(r["dst"])
        col = "#d5e8d4" if r["action"] == "allow" else "#f8cecc"
        det = []
        if "shape" in r:
            det.append("shape " + r["shape"])
        if "ports" in r:
            det.append("tcp " + "/".join(map(str, r["ports"])))
        if "note" in r:
            det.append(r["note"])
        rows += (f"<tr bgcolor='{col}'><td>{i}</td><td>{r['src']}</td><td>{dst}</td><td>{r['action']}</td><td>{'; '.join(det)}</td></tr>")
    d.box(40, 960, 740, 280,
          "<b>Firewall policy (plan order; deny rules are placed first in the FortiOS policy list, then catch-all deny)</b>"
          "<table border='1' cellpadding='3' style='border-collapse:collapse;font-size:11px'>"
          "<tr><th>#</th><th>source</th><th>destination</th><th>action</th><th>detail</th></tr>" + rows + "</table>",
          "white", "align=left;verticalAlign=top;spacingLeft=6;")
    d.save(HERE / "logical.drawio")


if __name__ == "__main__":
    physical()
    logical()
    print("wrote physical.drawio logical.drawio")
