# Requirements: Baan Chalong Residence network

> SIMULATED PROJECT. The client, the building, the owner and every number about them are made up for a portfolio project. No real customer.

## 1. Client brief (invented)

**Client:** Baan Chalong Residence, a fictional apartment near KMITL, Lat Krabang, Bangkok.
**Building:** 5 floors, 12 rooms per floor, 60 rooms. Rooms are numbered 101-112, 201-212 and so on.
**Owner:** Khun Somchai (persona). Not a network person. He runs the place with two office staff. He wants the network to stop causing complaints and wants to look at the cameras from his phone.
**Tenants:** mostly KMITL students. They stream, play games and do video calls. Peak is at night.
**Staff office:** ground floor. 3 PCs, 1 printer, 1 POS. Staff need internet and need to view the cameras.
**CCTV:** 24 IP cameras and one NVR. Today the cameras cannot be seen from outside.
**Lobby:** guest Wi-Fi with a captive portal for visitors and delivery riders.
**Internet:** two fibre lines, ISP-A 1000/500 Mbps (main) and ISP-B 500/500 Mbps (backup), both DHCP.
**Budget (invented):** about 320,000 THB for equipment and installation. This figure is made up. Real prices are in `bom/`.

### Complaints today

1. Wi-Fi is slow at night.
2. Tenants can see each other's devices (printers, NAS, laptops) on the network.
3. The CCTV cannot be reached from outside the building.
4. Owner also worries that tenants or guests could reach the office PCs and cameras.

## 2. Requirements

Each one can be tested. Test ids are in section 3.

### Functional

| ID | Requirement |
|---|---|
| R1 | Each floor has its own tenant VLAN and subnet (VLANs 101-105). A tenant device gets its address by DHCP from its floor scope. |
| R2 | Management, staff, CCTV, guest and tenant traffic are on separate VLANs (10, 20, 30, 40, 101-105). |
| R3 | A tenant device cannot reach a device in another tenant VLAN (other floors). |
| R4 | A device in room A cannot reach a device in room B on the same floor, wired or Wi-Fi. |
| R5 | Tenant devices cannot reach MGMT, STAFF, CCTV or GUEST. |
| R6 | Tenant devices reach the internet, limited to 100 Mbps down and 50 Mbps up per room. |
| R7 | Guest Wi-Fi in the lobby shows a captive portal before it gives internet. |
| R8 | Guest devices reach the internet only. They cannot reach any private address (RFC1918). |
| R9 | Guest devices are limited to 20 Mbps down and 10 Mbps up per client. |
| R10 | Staff devices reach the internet and reach the NVR/cameras on TCP 443 and 554 only. |
| R11 | CCTV devices have no internet access. |
| R12 | The owner connects by VPN from outside and reaches MGMT and CCTV. Nothing else is opened to the VPN. |
| R13 | Management interfaces (firewall, switches, APs) are reachable only from MGMT and the owner VPN. |
| R14 | If ISP-A fails, traffic moves to ISP-B without manual work. When ISP-A returns, traffic goes back. |
| R15 | Tenant Wi-Fi has one SSID per floor with WPA2/WPA3 and client isolation. |
| R16 | The 24 cameras and the NVR have fixed addresses and record to the NVR. |

### Non-functional

| ID | Requirement |
|---|---|
| R17 | Monitoring (Zabbix, SNMP) shows up/down of firewall, switches, APs, both WAN links and the camera ports. It sends an alert to the owner when a WAN link is down. |
| R18 | Configs of firewall, switches and Omada controller are backed up automatically at least once a week and after each change, and one copy is stored off the server. |
| R19 | No default passwords. Admin accounts are named, SNMP is v3, firmware is current at install time. |
| R20 | One failed access switch affects only that floor. |
| R21 | Everything is documented so a new person can find a port, an IP or a rule from the docs alone (hld, lld, ip-plan, handover). |
| R22 | The owner can do the routine jobs from the Thai handover sheet without calling the installer: add a tenant, change the guest password, check the cameras. |
| R23 | A tenant who streams does not slow down the other tenants: per-room limits make the sum of tenant limits (60 x 100 Mbps) above the main line on purpose, but one room can never take it all. |

R23 is the answer to complaint 1. The 6:1 ratio (60 x 100 / 1000) is a design choice. It is not tested against real tenants because the project is simulated.

## 3. Acceptance tests

| Test | Requirement | Where | Steps | Pass when |
|---|---|---|---|---|
| T1 VLAN isolation | R2, R3, R5 | from a laptop on floor 2 | ping and connect to a host on floor 3, to 10.20.10.1 (fw mgmt), to a staff PC, to nvr-01 | all fail or time out |
| T2 Per-room isolation (wired) | R4 | two laptops in rooms 201 and 202 | ping from one to the other | no reply, both still reach the gateway |
| T3 Per-room isolation (Wi-Fi) | R4, R15 | two phones on BCR-F2, same AP and different AP | ping each other | no reply |
| T4 Guest internet only | R7, R8 | phone on BCR-Guest | open a page, accept the portal, then try 10.20.10.1, 10.20.20.x, 10.21.1.x | internet works after portal, every private address fails |
| T5 Tenant bandwidth limit | R6, R23 | iperf3 to a test server outside, from one room | run 30 s down and 30 s up | down about 100 Mbps or less, up about 50 Mbps or less |
| T6 Guest bandwidth limit | R9 | iperf3 from a guest phone/laptop | same | down about 20 Mbps or less, up about 10 Mbps or less |
| T7 Owner VPN | R12, R13 | phone on mobile data, VPN on | open NVR page at 10.20.30.10, open fw GUI at 10.20.10.1, try a tenant subnet and a staff PC | NVR and fw GUI work, tenant subnet and staff PC fail |
| T8 CCTV no internet | R11 | from nvr-01 or a camera | ping 1.1.1.1 | fails |
| T9 Staff to CCTV | R10 | from a staff PC | open https://10.20.30.10, play RTSP stream, try SSH to nvr-01 | 443 and 554 work, other ports fail |
| T10 WAN failover | R14 | pull the ISP-A cable | ping 1.1.1.1 from a tenant, then reconnect | traffic returns within the health-check time, goes back to ISP-A after reconnect |
| T11 Management access | R13 | from a tenant laptop and from the admin port | open switch web/SSH | tenant fails, admin port works |
| T12 Monitoring and alert | R17 | unplug a switch uplink and pull a WAN cable | check Zabbix | host goes down in Zabbix, alert arrives |
| T13 Backup | R18 | check the backup folder and the off-server copy | look for files for fw, 6 switches and the controller | files exist and are dated within the last week |
| T14 Port map check | R21 | pick 5 random rooms | find the room port from lld.md and test the wall jack | port and VLAN match the table |

The lab in `lab/` is a software model of some of these tests. It does not replace the tests on real hardware. See `lab/` for which ones it covers.
