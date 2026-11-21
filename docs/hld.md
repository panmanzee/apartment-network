# High-level design

> SIMULATED PROJECT. Baan Chalong Residence is a fictional client. This design is a portfolio project, not a deployed network.

Source of truth for addresses and rules: `plan/ip-plan.yaml`. Details are in `lld.md` and `ip-plan.md`. Requirement ids (R1...) are from `requirements.md`.

## 1. Design decisions

| Decision | Choice | Why |
|---|---|---|
| Where inter-VLAN routing happens | On fw-edge (FortiGate). sw-core is layer 2 only. | Every VLAN gateway is on the firewall, so every rule is in one place. Denied traffic is logged in full (logtraffic all). Allow rules are set to logtraffic utm, but no security profile is applied in the rendered config, so allowed traffic is not logged yet. Fits R2-R13. |
| What the transit /30 is | 10.20.0.0/30, fw-edge .1, sw-core .2, in the yaml. Not used: the core is L2, so nothing is routed over it. VLAN 999 is an unused native/parking VLAN on the trunks, no user traffic. | The yaml has a transit net, but with an L2 core there is no place for it. sw-core is managed on VLAN 10 (10.20.10.2). |
| Room isolation | Protected ports on the switches plus client isolation on Wi-Fi | One subnet per floor, so the switch must block room to room. R4. |
| Tenant Wi-Fi | One SSID per floor, WPA2/WPA3 personal, client isolation | Simple for the owner. No RADIUS server to run. R15. |
| Guest | Own SSID on ap-lobby, captive portal on Omada, VLAN 40 | R7-R9. |
| Owner VPN | IPsec IKEv2 on fw-edge, pool 10.20.50.0/24 | The yaml says ipsec-or-wireguard. FortiGate does IPsec natively. The lab uses WireGuard to model it. |
| WAN | Dual WAN, ISP-A primary, ISP-B backup, health check failover | R14. |
| Monitoring | Zabbix on mon-01 (10.20.10.50), SNMPv3 | R17. mon-01 is not in the yaml, added here. |

## 2. Topology

```mermaid
flowchart TB
  ISPA[ISP-A FTTx 1000/500] --- FW
  ISPB[ISP-B FTTx 500/500] --- FW
  FW[fw-edge FortiGate<br/>gateways for all VLANs<br/>10.20.10.1] ---|LACP trunk, native VLAN 999 (unused)| CORE[sw-core L2<br/>10.20.10.2]
  CORE --- F1[sw-f1 .11]
  CORE --- F2[sw-f2 .12]
  CORE --- F3[sw-f3 .13]
  CORE --- F4[sw-f4 .14]
  CORE --- F5[sw-f5 .15]
  CORE --- NVR[nvr-01 10.20.30.10]
  CORE --- LAP[ap-lobby .41]
  CORE --- STAFF[Staff office VLAN 20]
  CORE --- MON[mon-01 .50 Zabbix]
  F1 --- R1[rooms 101-112]
  F1 --- A1[ap-f1-a, ap-f1-b]
  F1 --- C1[4 cameras]
  OWNER[Owner phone] -. IPsec VPN .-> FW
```

Floors 2 to 5 are built the same way as floor 1. The mon-01 server plugs into a MGMT port on sw-core.

Wiring (same as `configs/render.py` and `lld.md`): fw-edge `internal1` + `internal2` go to sw-core Gi1/0/1-2 as an LACP trunk (`lag-core`). sw-core Gi1/0/11-15 go to Gi1/0/24 on sw-f1 to sw-f5. Other core ports: 3 mon-01, 4 admin port, 5 nvr-01, 6 ap-lobby, 7-10 lobby cameras, 17-20 staff. A floor is a star: switch in the floor cupboard, one cable per room (Gi1/0/1-12), two APs (13-14), four cameras (15-18).

BOM note: the BOM uses two 16-channel NVRs for 24 cameras (nvr-01 and nvr-02). The plan and these docs only list nvr-01, so nvr-02 is not in the address plan or the port map.

## 3. VLANs

| VLAN | Name | Subnet | Notes |
|---|---|---|---|
| 10 | MGMT | 10.20.10.0/24 | switches, APs, firewall, mon-01. No DHCP. |
| 20 | STAFF | 10.20.20.0/24 | office PCs, printer, POS. |
| 30 | CCTV | 10.20.30.0/24 | 24 cameras and NVR. No DHCP, no internet. |
| 40 | GUEST | 10.20.40.0/24 | lobby Wi-Fi only. |
| 101-105 | TENANT-F1..F5 | 10.21.1.0/24 ... 10.21.5.0/24 | one per floor. |
| 999 | TRANSIT | 10.20.0.0/30 | added in the docs. Unused native/parking VLAN. The /30 is not used. |

Full table with gateways: `ip-plan.md`.

## 4. Security zones and policy

Zones: MGMT, STAFF, CCTV, GUEST, TENANT (five VLANs, treated as one zone name but never allowed to talk to each other), OWNER-VPN, internet.

Matrix from the yaml policy. A = allow, D = deny, blank = not allowed (default deny).

| From \ To | MGMT | STAFF | CCTV | GUEST | TENANT | internet |
|---|---|---|---|---|---|---|
| MGMT | - | | | | | A (firmware updates only) |
| STAFF | | - | A tcp 443, 554 | | | A |
| CCTV | | | - | | | D |
| GUEST | | | | - | | A, 20/10 Mbps per client; private ranges D |
| TENANT | D | D | D | D | D (also between floors) | A, 100/50 Mbps per device (see shaping note) |
| OWNER-VPN | A | | A | | | |

Rule order, NAT and logging are in `lld.md` section 6. Deny rules for private ranges come before internet allow rules.

Not allowed means no rule, so the last rule (implicit deny, logged) drops it.

Shaping note: a firewall sees IP addresses, not rooms. The firewall shaper is per IP address, so a room with three devices could use three times the limit. There is no per-port limit on the switches (not in the rendered configs), so the limit is per device, not per room. This is a known gap, written here on purpose.

## 5. Wi-Fi (TP-Link Omada)

- Omada controller (software, on mon-01 or a small mini PC) manages 11 APs on VLAN 10.
- Tenant: SSIDs `BCR-F1` to `BCR-F5`. WPA2/WPA3 personal, one password per floor, mapped to VLAN 101-105. Client isolation on. Both APs on a floor carry only that floor's SSID.
- Guest: SSID `BCR-Guest` on ap-lobby, VLAN 40, Omada portal with voucher or simple password, client isolation on, 20/10 Mbps per client.
- AP ports on the switch are protected, so a client on ap-f2-a cannot reach one on ap-f2-b through the switch.
- A per-floor password is a trade-off: simple for the owner, but a tenant who shares the password with a friend adds a device. 802.1X or PPSK would be the next step, left out on purpose to keep it simple.

## 6. CCTV

- 24 cameras: 4 per floor on the floor switch (ports 15-18), 4 on sw-core (gate, parking, lobby, back).
- All on VLAN 30, fixed addresses 10.20.30.101-124, NVR 10.20.30.10.
- No internet for CCTV (R11). The firewall serves NTP on MGMT only (as rendered), so CCTV has no NTP source yet. Planned: NTP on the CCTV interface plus a local-in rule, not in the configs.
- Staff view the NVR on TCP 443 and RTSP 554. Owner views it over the VPN. No port forward to the NVR from the internet.

## 7. Owner remote access

- IPsec IKEv2, FortiClient or the phone's built-in client. Pool 10.20.50.0/24.
- Split tunnel: only 10.20.10.0/24 and 10.20.30.0/24 go into the tunnel.
- Needs a public IP on a WAN. Many home fibre lines in Thailand sit behind CGNAT. The owner has to ask the ISP for a public IP (or use the line that has one). The WAN address is DHCP, so DDNS is used for the name.
- One account per person, no shared login. MFA (FortiToken) is planned, not in the rendered config.

## 8. Monitoring (Zabbix)

- mon-01 at 10.20.10.50 on MGMT. SNMPv3 to firewall, switches and APs.
- Items: device up/down, WAN link state and ping to two public hosts, port state of uplinks and camera ports, interface traffic, CPU of the firewall.
- Camera health is watched through switch port state. mon-01 is on MGMT and policy does not allow MGMT to CCTV, so it does not ping cameras directly.
- Alerts: Telegram bot or email to the owner and the installer. WAN down and a switch down are the two that wake someone.
- Syslog from the firewall goes to mon-01.

## 9. Backups

- Firewall config, switch configs and the Omada controller are backed up on mon-01 weekly and after each change.
- One copy goes off the server (owner's cloud drive). One USB copy is kept in the office each month.
- NetBox data is generated from the yaml, so it can be rebuilt with `netbox/gen.py` and `netbox/load.py`.
- NVR footage is not backed up. Retention depends on the disk (see `bom/`).
- Passwords are kept in a password manager and one sealed paper copy in the owner's safe. They are never in these docs.

## 10. Failure behaviour

| Failure | What happens |
|---|---|
| ISP-A down | firewall switches to ISP-B (500/500). Shapers stay the same. |
| Access switch down | that floor is offline only (R20). |
| sw-core down | whole building is offline. There is no second core. This is a known risk in the budget. |
| fw-edge down | whole building is offline. |
| mon-01 down | no monitoring or alerts. Network keeps working. |
