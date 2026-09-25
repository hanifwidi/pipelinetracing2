#!/usr/bin/env python3
"""Niche performance tracker - verdict DOUBLE-DOWN / HOLD / KILL"""
import csv, sys
from datetime import date, datetime
from pathlib import Path

LOG = Path("tracking/production_log.csv")

def cmd_report():
    if not LOG.exists():
        print(f"❌ {LOG} belum ada. Jalankan dulu: python init_tracking.py"); return
    rows = list(csv.DictReader(open(LOG, newline='', encoding='utf-8')))
    agg = {}
    for r in rows:
        a = agg.setdefault(r['niche'], dict(sub=0, acc=0, rej=0, pend=0, dl=0))
        a['sub'] += 1
        if r['status'] == 'accepted': a['acc'] += 1
        elif r['status'] == 'rejected': a['rej'] += 1
        else: a['pend'] += 1
        a['dl'] += max([int(r.get(c) or 0) for c in ('dl_30d','dl_60d','dl_90d')])
    print(f"\n{'NICHE':<14}{'SUB':>4}{'ACC':>4}{'REJ':>4}{'PEND':>5}{'RATE':>7}{'DL':>5}  VERDICT")
    for k, a in sorted(agg.items()):
        decided = a['acc'] + a['rej']
        rate = f"{a['acc']/decided*100:.0f}%" if decided else '-'
        verdict = '-'
        if decided >= 5:
            ratio = a['acc'] / decided
            verdict = 'DOUBLE-DOWN 🔥' if ratio >= 0.7 else 'KILL 💀' if ratio < 0.4 else 'HOLD ⏸'
        print(f"{k:<14}{a['sub']:>4}{a['acc']:>4}{a['rej']:>4}{a['pend']:>5}{rate:>7}{a['dl']:>5}  {verdict}")

if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "report"
    if c == "report": cmd_report()
