#!/usr/bin/env python3
"""Load netbox/import/netbox.yaml into a NetBox over REST. Safe to run many times.
usage: load.py --url http://localhost:8010 --token TOKEN [--export FILE]
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
counts = {}


class NB:
    def __init__(self, url, token):
        self.url = url.rstrip("/")
        self.h = {"Authorization": f"Token {token}", "Content-Type": "application/json",
                  "Accept": "application/json"}

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.url + path, method=method, headers=self.h,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            sys.exit(f"{method} {path} -> {e.code} {e.read().decode()[:400]}")

    def find(self, path, **q):
        qs = "&".join(f"{k}={v}" for k, v in q.items())
        res = self.call("GET", f"{path}?{qs}&limit=2")["results"]
        return res[0] if res else None

    def ensure(self, kind, path, lookup, body):
        got = self.find(path, **lookup)
        c = counts.setdefault(kind, {"created": 0, "existing": 0})
        if got:
            c["existing"] += 1
            return got
        c["created"] += 1
        return self.call("POST", path, body)


def expand(spec):
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def wait(nb):
    for _ in range(90):
        try:
            nb.call("GET", "/api/status/")
            return
        except SystemExit:
            pass
        except Exception:
            pass
        time.sleep(5)
    sys.exit("netbox api not ready")


def slug(s):
    return s.lower().replace(" ", "-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8010")
    ap.add_argument("--token", required=True)
    ap.add_argument("--export")
    a = ap.parse_args()
    d = yaml.safe_load((HERE / "import" / "netbox.yaml").read_text())
    nb = NB(a.url, a.token)
    wait(nb)

    site = nb.ensure("site", "/api/dcim/sites/", {"slug": d["site"]["slug"]},
                     {"name": d["site"]["name"], "slug": d["site"]["slug"], "status": "active",
                      "description": "SIMULATED client, fictional"})
    man = {m: nb.ensure("manufacturer", "/api/dcim/manufacturers/", {"slug": slug(m)},
                        {"name": m, "slug": slug(m)}) for m in d["manufacturers"]}
    role = {}
    for r in d["device_roles"]:
        role[r] = nb.ensure("device_role", "/api/dcim/device-roles/", {"slug": r}, {"name": r, "slug": r})
    dtype, role_of_model = {}, {}
    for t in d["device_types"]:
        dtype[t["role"]] = nb.ensure("device_type", "/api/dcim/device-types/", {"slug": slug(t["model"])},
                                     {"manufacturer": man[t["manufacturer"]]["id"], "model": t["model"],
                                      "slug": slug(t["model"])})
    vlan = {}
    for v in d["vlans"]:
        vlan[v["vid"]] = nb.ensure("vlan", "/api/ipam/vlans/", {"site_id": site["id"], "vid": v["vid"]},
                                   {"site": site["id"], "vid": v["vid"], "name": v["name"],
                                    "status": "active", "description": v["desc"]})
    for p in d["prefixes"]:
        body = {"prefix": p["prefix"], "status": "active", "scope_type": "dcim.site",
                "scope_id": site["id"], "description": p["desc"]}
        if p["vid"]:
            body["vlan"] = vlan[p["vid"]]["id"]
        nb.ensure("prefix", "/api/ipam/prefixes/", {"prefix": p["prefix"]}, body)
    dev = {}
    for x in d["devices"]:
        dev[x["name"]] = nb.ensure("device", "/api/dcim/devices/", {"name": x["name"]},
                                   {"name": x["name"], "role": role[x["role"]]["id"],
                                    "device_type": dtype[x["role"]]["id"], "site": site["id"],
                                    "status": "active"})
    ifc = {}
    for i in d["interfaces"]:
        body = {"device": dev[i["device"]]["id"], "name": i["name"], "type": i["type"],
                "description": i["desc"]}
        if i["mode"]:
            body["mode"] = i["mode"]
            if i.get("untagged"):
                body["untagged_vlan"] = vlan[int(i["untagged"])]["id"]
            if i.get("tagged"):
                body["tagged_vlans"] = [vlan[v]["id"] for v in expand(i["tagged"])]
        ifc[(i["device"], i["name"])] = nb.ensure("interface", "/api/dcim/interfaces/",
                                                  {"device_id": body["device"], "name": i["name"]}, body)
    for ip in d["ip_addresses"]:
        body = {"address": ip["address"], "status": ip["status"], "dns_name": ip["dns"],
                "description": ip["desc"]}
        if ip["device"]:
            body["assigned_object_type"] = "dcim.interface"
            body["assigned_object_id"] = ifc[(ip["device"], ip["iface"])]["id"]
        obj = nb.ensure("ip_address", "/api/ipam/ip-addresses/", {"address": ip["address"]}, body)
        if ip["primary"] and ip["device"]:
            dv = dev[ip["device"]]
            if not (nb.call("GET", f"/api/dcim/devices/{dv['id']}/").get("primary_ip4")):
                nb.call("PATCH", f"/api/dcim/devices/{dv['id']}/", {"primary_ip4": obj["id"]})
                counts.setdefault("primary_ip4_set", {"created": 0, "existing": 0})["created"] += 1
            else:
                counts.setdefault("primary_ip4_set", {"created": 0, "existing": 0})["existing"] += 1

    total_new = sum(c["created"] for c in counts.values())
    for k, c in counts.items():
        print(f"{k:16} created={c['created']:4} existing={c['existing']:4}")
    print(f"TOTAL created={total_new}")

    if a.export:
        out = {}
        for k, p in [("sites", "dcim/sites"), ("vlans", "ipam/vlans"), ("prefixes", "ipam/prefixes"),
                     ("devices", "dcim/devices"), ("ip_addresses", "ipam/ip-addresses")]:
            res = nb.call("GET", f"/api/{p}/?limit=1000")
            out[k] = {"count": res["count"]}
        out["vlans"]["items"] = [[v["vid"], v["name"]] for v in nb.call("GET", "/api/ipam/vlans/?limit=1000&ordering=vid")["results"]]
        out["prefixes"]["items"] = [[p["prefix"], (p["vlan"] or {}).get("name")] for p in nb.call("GET", "/api/ipam/prefixes/?limit=1000&ordering=prefix")["results"]]
        out["devices"]["items"] = [[x["name"], x["role"]["name"], (x["primary_ip4"] or {}).get("address")] for x in nb.call("GET", "/api/dcim/devices/?limit=1000&ordering=name")["results"]]
        out["interfaces"] = {"count": nb.call("GET", "/api/dcim/interfaces/?limit=1")["count"]}
        Path(a.export).write_text(json.dumps(out, indent=1))
        print("export written", a.export)


if __name__ == "__main__":
    main()
