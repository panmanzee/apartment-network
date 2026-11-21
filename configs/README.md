# configs

Vendor configs for the simulated 5-floor / 60-room apartment (FortiGate 60F edge + Cisco Catalyst IOS switches), generated from `../plan/ip-plan.yaml`.

**Status: generated and statically checked only. These configs have NOT been run on real FortiGate or Cisco hardware, nor on FortiGate-VM / IOS images** (those need vendor accounts). Syntax such as the exact `set` keywords for FortiOS 7.4 and the IOS feature set of the target Catalyst model are written from documentation and could still need small fixes on a real box.

## Layout

| path | what |
| --- | --- |
| `render.py` | reads the yaml, renders everything below with the Jinja templates |
| `templates/*.j2` | `fw-edge.conf.j2`, `sw-core.cfg.j2`, `sw-access.cfg.j2`, shared `ios-base.j2` / `ios-tail.j2` |
| `out/fortigate/fw-edge.conf` | FortiOS CLI |
| `out/cisco/sw-core.cfg`, `sw-f1..f5.cfg` | IOS |
| `ansible/` | inventory (also rendered), roles `fortigate` + `cisco_access`, `site.yml` |
| `check.py` | static property checks, writes `results/check-<date>.log` |
| `results/` | check log, ansible syntax-check + lint logs, md5 of the rendered files |

```
python3 -m venv .venv && .venv/bin/pip install ansible-core ansible-lint ciscoconfparse2 pyyaml jinja2
.venv/bin/ansible-galaxy collection install -r ansible/requirements.yml -p .collections
.venv/bin/python render.py     # same yaml in, byte-identical files out
.venv/bin/python check.py
cd ansible && ../.venv/bin/ansible-playbook --syntax-check site.yml && ../.venv/bin/ansible-lint
```

## Design choices

- The configs target the FortiGate + Cisco design (close to BOM option A). The BOM recommends option C (TP-Link Omada), which has no rendered config here.
- The firewall does the inter-VLAN routing: `lag-core` (LACP, internal1+internal2) carries a subinterface per VLAN, `sw-core` is layer 2 only (`no ip routing`, SVI only in VLAN 10). That is what makes the yaml policy enforceable. The plan's transit net `10.20.0.0/30` is therefore not used.
- Port map is not in the yaml, so it lives in `render.py` (this is the one source for the port maps in the docs): core Gi1/0/1-2 = fw LAG (internal1+2), 3 = mon-01, 4 = admin port, 5 = NVR, 6 = lobby AP, 7-10 = lobby cams, 11-15 = floor uplinks (sw-f1..f5), 17-20 = staff, rest shut down. Access switches follow the yaml (rooms 1-12, APs 13-14, cams 15-18, uplink 24, rest shut down in VLAN 999).
- Values not in the yaml, set as defaults in `render.py`: syslog/NMS host `10.20.10.50` (mon-01), admin user `netadmin`, domain `baan-chalong.lan`, upstream NTP pools. Switches take NTP from the firewall (10.20.10.1).
- Secrets are placeholders (`__ADMIN_PASS__`, `__SNMP_AUTH__`, ...). The ansible roles substitute them from `group_vars/all/vault.yml` (see `vault.yml.example`, encrypt with ansible-vault).
- Policy order: deny rules first, then allows, then a catch-all deny. This is needed because GUEST->internet would otherwise match before GUEST->RFC1918 (the checker caught that on the first render).
- Switch VTY access is limited to the MGMT subnet; the owner VPN can reach MGMT at the firewall, but would need a jump host to SSH to switches.

## Known gaps

- Tenant 100/50 and guest 20/10 Mbps: a FortiOS per-IP shaper applies one limit in both directions. `render.py` sets it to the download figure (100 / 20 Mbps per IP), so the 50 / 10 Mbps upload limit is **not** enforced. Asymmetric per-IP needs another mechanism; to be tested on a real unit.
- Captive portal is only the interface setting plus an empty guest group; no portal page, no voucher users.
- Tenants and staff can still reach private addresses that sit on the WAN side (for example an ISP modem at 192.168.x.x); the plan only blocks that for GUEST.
- The ansible `fortigate` role pushes the CLI text with `raw` over SSH (the fortios collection has no bulk-CLI module) and does an optional REST read-back if `fortios_access_token` is set. Neither role was run against a device.
- Batfish was not run (not set up; no IOS images).

## What check.py covers (335 checks)

IOS, every switch: hostname, rapid-pvst, SSH-only VTY with ACL, no telnet/http, SNMPv3 only, NTP, logging, banner, mgmt SVI IP from the yaml.
Access: each of the 12 room ports is access VLAN 10N for that floor, description matches the room number, `switchport protected`, port-security, storm-control, portfast+bpduguard, and no other port is in the tenant VLAN; AP ports are `switchport protected` and trunk with native 10 and allowed `{10,40,10N}`; camera ports VLAN 30; uplink trunk allowed exactly `{10,30,40,10N}`; spare ports shut.
Core: lobby AP port protected, mon-01 and admin ports in VLAN 10, STP priority 4096, Po1 allowed all plan VLANs, floor trunk lists equal the access-side uplink lists.
FortiOS: VLAN subinterfaces and IPs vs yaml, admin access only on MGMT, DHCP servers exactly on `dhcp: true` VLANs, trusthost, SNMPv3, SD-WAN members, dial-up IPsec pool and split-include, every yaml policy rule has a policy with the right action, shaper applied, plus 28 first-match flow tests (for example tenant->tenant deny, staff->CCTV tcp 22 deny, VPN->STAFF deny).
