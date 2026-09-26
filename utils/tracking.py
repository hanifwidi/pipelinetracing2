"""Non-destructive production tracking and dated cumulative observations."""
import csv
import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from filelock import FileLock
from utils.atomic_io import write_csv

FIELDS = ['filename','asset_id','adobe_asset_id','niche','style','batch_date','submitted',
          'status','pipeline_status','reject_reason','accepted_date','first_seen_accepted',
          'dl_30d','dl_60d','dl_90d','notes','dl_latest','dl_date','royalty_usd','production_seconds']
SNAPSHOT_FIELDS = ['filename','observed_date','downloads','royalty_usd']


def read_table(path):
    path = Path(path)
    if not path.exists():
        return [], []
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        return list(reader), list(reader.fieldnames or [])


def save_log(path, rows, old_fields=()):
    fields = list(dict.fromkeys(FIELDS + list(old_fields) + [k for r in rows for k in r]))
    write_csv(path, fields, rows)


def parse_date(value):
    if not value:
        return None
    return date.fromisoformat(str(value).strip()[:10])


def extract_niche_style_batch(filename):
    stem = re.sub(r'__[0-9a-f]{12,64}$', '', Path(filename).stem.lower())
    words = re.split(r'[_\s-]+', stem)
    style = next((s for s in ('blue', 'line', 'solid', 'outline') if s in words), '')
    match = re.search(r'(?<!\d)(20\d{6})(?:\d{6})?(?!\d)', stem)
    batch = ''
    if match:
        try:
            batch = datetime.strptime(match[1], '%Y%m%d').date().isoformat()
        except ValueError:
            pass
    return words[0] if words else '', style, batch


def initialize_tracking(metadata_path, log_path, niche=None):
    metadata_path, log_path = Path(metadata_path), Path(log_path)
    if not metadata_path.exists():
        raise FileNotFoundError(metadata_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(log_path) + '.lock', timeout=30):
        existing, fields = read_table(log_path)
        rows = {r['filename']: r for r in existing}
        metadata, _ = read_table(metadata_path)
        added = 0
        for item in metadata:
            fn = item['Filename']
            if fn in rows:
                continue
            guess, style, batch = extract_niche_style_batch(fn)
            rows[fn] = dict(filename=fn, niche=niche or guess, style=style,
                            batch_date=batch, status='ready', notes='Initialized from metadata; submission unconfirmed')
            added += 1
        save_log(log_path, list(rows.values()), fields)
    return added


def record_asset(log_path, filename, values):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(log_path) + '.lock', timeout=30):
        old, fields = read_table(log_path)
        rows = {r['filename']: r for r in old}
        niche, style, batch = extract_niche_style_batch(filename)
        row = rows.setdefault(filename, dict(filename=filename, niche=niche, style=style, batch_date=batch,
                                            status=values.get('pipeline_status', 'ready')))
        if row.get("status") in {"ready", "needs_metadata", "needs_review", "failed"}:
            row["status"] = values.get("pipeline_status", row["status"])
        # Pipeline output cannot reset a human-entered submission/acceptance history.
        for key, value in values.items():
            if key not in {'status','accepted_date','submitted','reject_reason','notes','dl_latest','royalty_usd'}:
                if key in {'niche','style'} and row.get(key):
                    continue
                row[key] = value
        save_log(log_path, list(rows.values()), fields)


def import_downloads(scrape_path, metadata_path, log_path):
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(log_path) + '.lock', timeout=30):
        records, fields = read_table(log_path)
        rows = {r['filename']: r for r in records}
        metadata, _ = read_table(metadata_path)
        titles = defaultdict(set)
        norm = lambda value: ' '.join(str(value).lower().split())
        for item in metadata:
            titles[norm(item.get('Title', ''))].add(item['Filename'])
        scrape, _ = read_table(scrape_path)
        history_path = log_path.parent / 'download_history.csv'
        existing, _ = read_table(history_path)
        history = {(r['filename'], r['observed_date']): r for r in existing}
        counts = dict(matched=0, ambiguous=0, unmatched=0, invalid=0)
        for item in scrape:
            external_id = item.get('adobe_asset_id') or item.get('asset_id') or item.get('id')
            candidates = {r['filename'] for r in rows.values() if external_id and r.get('adobe_asset_id') == external_id}
            if not candidates:
                direct = item.get('filename') or item.get('Filename')
                if direct and (direct in rows or any(m['Filename'] == direct for m in metadata)):
                    candidates = {direct}
                else:
                    candidates = titles.get(norm(item.get('title', '')), set())
            if len(candidates) != 1:
                counts['ambiguous' if len(candidates) > 1 else 'unmatched'] += 1
                continue
            fn = next(iter(candidates))
            # Never remap an already known Adobe asset using a coincidental title match.
            if external_id and rows.get(fn, {}).get('adobe_asset_id') not in {None, '', external_id}:
                counts['ambiguous'] += 1; continue
            try:
                observed = parse_date(item.get('last_seen') or item.get('observed_date'))
                downloads = int(item['downloads'])
                accepted = parse_date(item.get('accepted_date'))
                royalty = item.get('royalty_usd', '')
                if observed is None or downloads < 0 or (accepted and accepted > observed):
                    raise ValueError('Invalid observation')
                if royalty != '' and (float(royalty) < 0 or not math.isfinite(float(royalty))):
                    raise ValueError('Invalid royalty')
            except (ValueError, TypeError, KeyError):
                counts['invalid'] += 1; continue
            niche, style, batch = extract_niche_style_batch(fn)
            row = rows.setdefault(fn, dict(filename=fn, niche=niche, style=style, batch_date=batch, status='unknown'))
            stamp = observed.isoformat()
            snapshot = dict(filename=fn, observed_date=stamp, downloads=downloads, royalty_usd=royalty)
            previous = history.get((fn, stamp), {})
            # Daily snapshots cannot order two observations without timestamps.
            # Do not silently replace a higher same-day count with an older scrape.
            if previous and downloads < int(previous['downloads']):
                counts['invalid'] += 1
                continue
            if royalty == '':
                snapshot['royalty_usd'] = previous.get('royalty_usd', '')
            history[(fn, stamp)] = snapshot
            if external_id:
                row['adobe_asset_id'] = external_id
            if accepted and not row.get('accepted_date'):
                row['accepted_date'] = accepted.isoformat()
            explicit = item.get('status', '').strip().lower()
            accepted_evidence = explicit == 'accepted' or accepted is not None or downloads > 0
            if accepted_evidence:
                first = row.get('first_seen_accepted', '')
                row['first_seen_accepted'] = min(first, stamp) if first else stamp
            if not row.get('dl_date') or observed >= parse_date(row['dl_date']):
                row['dl_latest'], row['dl_date'] = downloads, stamp
                if royalty != '':
                    row['royalty_usd'] = royalty
                if explicit in {'accepted', 'rejected', 'submitted', 'pending'}:
                    row['status'] = explicit
                elif accepted_evidence:
                    row['status'] = 'accepted'
                # in_review=0 alone does not prove acceptance.
            counts['matched'] += 1
        write_csv(history_path, SNAPSHOT_FIELDS, [history[k] for k in sorted(history)])
        save_log(log_path, list(rows.values()), fields)
    return counts


def _recent_downloads(history, as_of, days=30):
    points = sorted((parse_date(r['observed_date']), int(r['downloads'])) for r in history
                    if parse_date(r['observed_date']) <= as_of)
    if not points or (as_of - points[-1][0]).days > 7:
        return None
    end_date, end_count = points[-1]
    cutoff = end_date - timedelta(days=days)
    # A real observed window, never divide lifetime counts by a guessed age.
    eligible = [(d,n) for d,n in points if cutoff - timedelta(days=7) <= d <= cutoff]
    if not eligible:
        return None
    start_date, start_count = eligible[-1]
    if end_count < start_count:
        return None  # Corrections/reset counters need manual review.
    return (end_count - start_count) * days / (end_date-start_date).days


def build_report(log_path, as_of=None, min_assets=10):
    as_of = as_of or date.today()
    with FileLock(str(log_path) + '.lock', timeout=30):
        records, _ = read_table(log_path)
        snapshots, _ = read_table(Path(log_path).parent / 'download_history.csv')
    history = defaultdict(list)
    for sample in snapshots:
        history[sample['filename']].append(sample)
    groups = {}
    for row in records:
        a = groups.setdefault(row.get('niche') or 'unclassified', dict(assets=0, accepted=0, rejected=0, downloads=0,
                            royalty_usd=0.0, royalty_known=0, observed_assets=0, recent_downloads=0.0, min_age_days=None))
        a['assets'] += 1
        a['accepted'] += row.get('status') == 'accepted'
        a['rejected'] += row.get('status') == 'rejected'
        value = row.get('dl_latest')
        a['downloads'] += int(value) if value not in {None, ''} else max(int(row.get(k) or 0) for k in ('dl_30d','dl_60d','dl_90d'))
        if row.get('royalty_usd') not in {None, ''}:
            a['royalty_usd'] += float(row['royalty_usd']); a['royalty_known'] += 1
        born = parse_date(row.get('accepted_date') or row.get('first_seen_accepted'))
        if born and row.get('status') == 'accepted':
            age = max(0, (as_of-born).days)
            a['min_age_days'] = age if a['min_age_days'] is None else min(age, a['min_age_days'])
        recent = _recent_downloads(history[row['filename']], as_of)
        if recent is not None and row.get('status') == 'accepted':
            a['observed_assets'] += 1; a['recent_downloads'] += recent
    for a in groups.values():
        decided = a['accepted'] + a['rejected']
        a['acceptance_rate'] = a['accepted']/decided if decided else None
        a['downloads_per_observed_asset_30d'] = a['recent_downloads']/a['observed_assets'] if a['observed_assets'] else None
        a['verdict'] = 'HOLD: insufficient observations'
        if decided >= min_assets and a['acceptance_rate'] < 0.4:
            a['verdict'] = 'FIX QUALITY'
        elif a['observed_assets'] >= min_assets:
            value = a['downloads_per_observed_asset_30d']
            if value >= 1 and a['acceptance_rate'] is not None and a['acceptance_rate'] >= 0.7:
                a['verdict'] = 'EXPAND TEST'
            elif value == 0:
                a['verdict'] = 'REVIEW NICHE'
            else:
                a['verdict'] = 'HOLD: monitor demand'
    return groups
