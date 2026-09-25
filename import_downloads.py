# import_downloads.py
import csv, sys, re
from datetime import date, datetime
from pathlib import Path

SCRAPE = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(Path('.').glob('adobe_scrape_*.csv'))[-1]
META, LOG = Path('output_svg/metadata.csv'), Path('tracking/production_log.csv')
norm = lambda s: re.sub(r'\s+', ' ', s.strip().lower())

t2f = {}
with open(META, newline='', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        t2f[norm(r['Title'])] = r['Filename']

fields = ['filename','niche','style','batch_date','submitted','status','reject_reason',
          'accepted_date','dl_30d','dl_60d','dl_90d','notes','dl_latest','dl_date']
rows = {}
if LOG.exists():
    with open(LOG, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows[r['filename']] = r

matched = changed = 0
with open(SCRAPE, newline='', encoding='utf-8') as f:
    for s in csv.DictReader(f):
        fn = t2f.get(norm(s['title']))
        if not fn: continue
        matched += 1
        r = rows.setdefault(fn, {k: '' for k in fields}); r['filename'] = fn
        old, new = int(r.get('dl_latest') or 0), int(s['downloads'] or 0)
        r['dl_latest'], r['dl_date'] = new, s['last_seen']
        if new != old: changed += 1
        if r.get('accepted_date'):
            days = (date.today() - datetime.strptime(r['accepted_date'], '%Y-%m-%d').date()).days
            r['dl_30d' if days <= 45 else 'dl_60d' if days <= 75 else 'dl_90d'] = new
        if s['in_review'] != '1' and r.get('status') in ('', 'submitted'):
            r['status'] = 'accepted'

with open(LOG, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows.values())
print(f'Matched {matched} aset | {changed} perubahan download | log: {LOG}')