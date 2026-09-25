#!/usr/bin/env python3
"""Initialize production_log dari metadata.csv - jalankan SEKALI saat pertama kali setup tracking"""
import csv, re
from pathlib import Path
from datetime import datetime

META, LOG = Path('output_svg/metadata.csv'), Path('tracking/production_log.csv')
LOG.parent.mkdir(parents=True, exist_ok=True)

def extract_niche_style_batch(filename):
    parts = filename.lower().replace('_', ' ').split()
    niche = parts[0] if parts else ''
    style = 'blue' if 'blue' in filename.lower() else 'line' if 'line' in filename.lower() else 'solid'
    digits = ''.join(c for c in filename if c.isdigit())
    batch = digits[-14:][:8] if len(digits) >= 8 else ''
    return niche, style, batch

fields = ['filename','niche','style','batch_date','submitted','status','reject_reason',
          'accepted_date','dl_30d','dl_60d','dl_90d','notes','dl_latest','dl_date']

with open(META, newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

with open(LOG, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
    for r in rows:
        fn = r['Filename']
        niche, style, batch = extract_niche_style_batch(fn)
        batch_date = f"{batch[:4]}-{batch[4:6]}-{batch[6:8]}" if len(batch) == 8 else ''
        w.writerow({
            'filename': fn,
            'niche': niche,
            'style': style,
            'batch_date': batch_date,
            'submitted': str(datetime.now().date()) if batch_date else '',
            'status': 'submitted',
            'reject_reason': '',
            'accepted_date': '',
            'dl_30d': '', 'dl_60d': '', 'dl_90d': '',
            'notes': 'initialized from metadata.csv',
            'dl_latest': 0,
            'dl_date': ''
        })

print(f"✅ Initialized {len(rows)} aset di {LOG}")
