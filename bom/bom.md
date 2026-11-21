# BOM: Baan Chalong Residence (simulated)

Prices checked 2026-11-21, may change. All prices THB incl. VAT 7% unless noted. Full source text in `sources.md`, machine-readable lines in `bom.csv`, totals recomputed by `python3 total.py`.

Scope: 1 firewall, 6 switches (1 core + 5 floor, 24 port), 11 APs, 24 cameras, NVR, UPS per rack (6), SFP modules for the 5 fibre links. Not included: cable, patch cords, racks, install labour, ISP fees. Many prices are Thai retail shop prices for 1 piece; project/bulk quotes would be lower.

Things I changed from the plan: 24 cameras need 2 x 16ch NVRs (plan lists one NVR, so that line is optional anyway). Core switch uses the same model as floor switches in B and C to keep spare parts simple.

## Option A: Cisco + FortiGate 40F
| Item | Model | Qty | Unit | Total | Source | Status |
|---|---|---|---|---|---|---|
| Firewall (1yr FortiCare+UTP) | FortiGate 40F FG-40F-BDL-950-12 | 1 | 40,660 | 40,660 | S8 | listed |
| Core switch | Cisco C1000-24T-4G-L | 1 | 21,293 | 21,293 | S5 | 19,900 ex VAT x1.07 |
| Floor switch PoE+ | Cisco C1000-24P-4G-L | 5 | 29,000 | 145,000 | S6 | listed |
| AP Wi-Fi 6 | Cisco CBW150AX-S-UK | 11 | 5,600 | 61,600 | S7 | listed (jib shows out of stock) |
| Camera 3MP | TP-Link VIGI C430 | 24 | 1,190 | 28,560 | S13 | listed |
| NVR 16ch | VIGI NVR1016H | 2 | 2,790 | 5,580 | S14 | listed |
| HDD 4TB | WD Purple WD44PURZ | 2 | 6,330 | 12,660 | S15 | listed |
| UPS 1000VA | APC BV1000I-MS | 6 | 2,990 | 17,940 | S16 | listed |
| SFP 1G LC | TP-Link TL-SM311LM | 10 | 1,306 | 13,060 | S17 | converted (EUR) |
| Meraki / Catalyst 9100 APs | - | - | - | - | - | quote needed, excluded |

**Total A: 346,353 THB** (13,060 converted). No controller needed: CBW150AX runs a "primary AP" mode and is managed from a phone app. Cisco-branded SFPs are not priced.

## Option B: Huawei + FortiGate 60F
| Item | Model | Qty | Unit | Total | Source | Status |
|---|---|---|---|---|---|---|
| Firewall (1yr) | FortiGate 60F FG-60F-BDL-950-12 | 1 | 46,545 | 46,545 | S9 | listed |
| Core + floor switch | Huawei S5735-L24P4S-A-V2 | 6 | 23,851 | 143,106 | S11 | converted (HKD) |
| AP Wi-Fi 6 | Huawei AirEngine 5761-11W (wall plate) | 11 | 4,505 | 49,555 | S12 | converted (USD) |
| Camera, NVR, HDD, UPS, SFP | same as A | | | 77,800 | S13-S17 | listed / SFP converted |
| Huawei AC / CloudCampus controller | - | 1 | - | - | - | quote needed, excluded |
| Huawei USG firewall | - | - | - | - | - | quote needed, not used |

**Total B: 317,006 THB** (205,721 of it is converted, so this one is the least reliable). It is also incomplete: the controller is missing, so real B is higher. I found no Thai shop price for Huawei switches or APs.

## Option C: TP-Link Omada
| Item | Model | Qty | Unit | Total | Source | Status |
|---|---|---|---|---|---|---|
| Router/firewall dual WAN | Omada ER8411 | 1 | 19,930 | 19,930 | S2 | listed |
| Core + floor switch | TL-SG3428XMP (24 PoE+ 384W, 4 SFP+) | 6 | 14,900 | 89,400 | S4 | listed (aggregator card) |
| AP Wi-Fi 6 ceiling | Omada EAP650 | 11 | 3,390 | 37,290 | S1 | listed |
| Controller | Omada OC200 | 1 | 3,190 | 3,190 | S3 | listed |
| Camera, NVR, HDD, UPS, SFP | same as A | | | 77,800 | S13-S17 | listed / SFP converted |

**Total C: 227,610 THB** (13,060 converted). Option C variant: swap ER8411 for FortiGate 40F (40,660) if the owner wants UTP filtering: total becomes 248,340.

## Firewall comparison (not in the totals)
| Model | Price THB | Includes | Status |
|---|---|---|---|
| FortiGate 40F | 40,660 (1yr) / 50,611 (3yr promo) | FortiCare 24x7 + UTP | listed (S8, S10) |
| FortiGate 60F | 46,545 (1yr) / 65,805 (3yr promo) | FortiCare 24x7 + UTP | listed (S9, S10) |
| Palo Alto PA-410 | 28,153 hardware only; 46,318 with 1yr support + ATP + URL + WildFire | see S20, S22 | converted (US / HK shops) |
| Palo Alto PA-440 | 52,803 hardware only | subscriptions quote needed | converted (S21) |

Notes:
- Both vendors sell the security features (IPS, AV, URL filter) as a yearly subscription tied to support. I did not find a Thai price for Palo Alto subscriptions, so the PA lines are rough.
- Palo Alto has no public Thai price. In my search PaloGuard did not sell outside the US/Canada and the HK bundle only gives RMA in HK/Macau, so these are only a rough guide. Ask a Thai distributor for a quote.
- FortiGate 40F: 5 Gbps firewall but 600 Mbps threat protection with UTP on (figures on S8). That is below the 1 Gbps ISP-A line, so if IPS is on, the 60F (700 Mbps, S9) is only a small step up. Both are fine with UTP off.
- PA-410 is 0.8 Gbps threat prevention, PA-440 is 1.2 Gbps (from the thietbimang.com listing); I did not use that site for prices.

## 3-year cost
Only the firewall licence changes in A and B. Swapping the 1yr bundle for the 3yr promo bundle (S10, pay 2 years get 3, to 15 Dec 2026):
- A: 356,304 THB
- B: 336,266 THB (still without the Huawei controller)
- C: 227,610 THB (Omada controller and ER8411 have no licence fee). Cisco CBW150AX and Omada have no subscriptions either.
Meraki would add a yearly licence per AP (not priced).

## Recommendation: Option C (TP-Link Omada), with FortiGate 40F if filtering is wanted
- Budget: about 120k cheaper than A and 90k cheaper than B (B is not even complete). With the 40F swap it is 248,340, still cheapest.
- Staff: one Omada controller (OC200) shows switches, APs and router in one page, with captive portal for the lobby guest Wi-Fi and per-client rate limit. Cisco CBW150AX plus C1000 switches are 2 different tools and the C1000 is CLI work.
- Local support: all TP-Link items I found are sold by many Thai shops (advice, jib-type retailers) with lifetime or 3-year warranty, so a spare can be bought same day. Cisco is also easy to buy in Thailand. Huawei switches and APs: I could not find a single Thai shop price, so support is unclear.
- Weak points of C: ER8411 is a router with SPI firewall, no UTP. The 24-port switch PoE budget (384W) is more than the floor needs (about 50W). The SG3428XMP price came from an aggregator card, so confirm with the shop.
- A is the "name on the CV" option and its price is Thai-listed except the SFP modules (13,060, converted from EUR). B is left as a comparison only until a Thai quote exists.

## Known gaps
- Converted: Huawei S5735 (HKD), AirEngine 5761-11W (USD), SFP modules (EUR), Palo Alto lines (USD/HKD).
- Quote needed (excluded): Huawei controller, Huawei USG, Meraki/Catalyst 9100, Palo Alto subscriptions for PA-440.
- Cisco CBW150AX at jib was out of stock on the page (price dated 2026-09-28).
