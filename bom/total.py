#!/usr/bin/env python3
"""Recompute BOM totals from bom.csv. Rows with in_total=no or no unit price are skipped."""
import csv, os, sys
here = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(here, "bom.csv"), encoding="utf-8")))
bad = 0
for r in rows:  # check converted/ex-VAT rows reproduce their unit price
    if r["status"].startswith("converted") or r["status"].startswith("listed (ex"):
        exp = round(float(r["listed_price"]) * float(r["fx_or_vat"]))
        if exp != int(r["unit_price_thb"]):
            print("MISMATCH", r["model"], exp, r["unit_price_thb"]); bad += 1
tot = {}; cnt = {}
for r in rows:
    if r["option"] not in "ABC" or r["in_total"] != "yes" or not r["unit_price_thb"]:
        continue
    line = int(r["qty"]) * int(r["unit_price_thb"])
    tot[r["option"]] = tot.get(r["option"], 0) + line
    if r["status"] == "converted":
        cnt.setdefault(r["option"], 0); cnt[r["option"]] += line
for o in "ABC":
    print(f"Option {o}: {tot[o]:,} THB  (of which converted-price lines: {cnt.get(o,0):,})")
def unit(model): return int(next(r for r in rows if r["model"] == model and r["option"] == "FW")["unit_price_thb"])
a3 = tot["A"] - unit("FG-40F-BDL-950-12") + unit("FortiGate 40F")
b3 = tot["B"] - unit("FG-60F-BDL-950-12") + unit("FortiGate 60F")
print(f"3-year (firewall swapped to 3yr promo bundle): A {a3:,}  B {b3:,}  C {tot['C']:,}")
print("Firewall comparison (THB, not in totals):")
for r in rows:
    if r["option"] == "FW":
        print(f"  {r['item']}: {int(r['unit_price_thb']):,}  [{r['status']}]")
sys.exit(1 if bad else 0)
