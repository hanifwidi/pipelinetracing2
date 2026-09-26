import csv
from datetime import date, timedelta
from utils.atomic_io import write_csv
from utils.tracking import initialize_tracking, import_downloads, read_table, build_report, extract_niche_style_batch, save_log, SNAPSHOT_FIELDS

def metadata(path, duplicate=False):
    rows=[dict(Filename='a.svg',Title='Cyber icon set',Keywords='cyber,icon,security,lock,shield',Category='')]
    if duplicate: rows.append({**rows[0], 'Filename':'b.svg'})
    write_csv(path, list(rows[0]), rows)

def scrape(path, rows):
    write_csv(path, list(dict.fromkeys(k for r in rows for k in r)), rows)

def test_init_twice_preserves_accepted_downloads_and_custom_fields(tmp_path):
    meta, log = tmp_path/'metadata.csv', tmp_path/'production_log.csv'
    metadata(meta)
    save_log(log,[dict(filename='old.svg',status='accepted',dl_latest='60',notes='keep me',custom='preserve')])
    assert initialize_tracking(meta,log) == 1
    assert initialize_tracking(meta,log) == 0
    rows,_=read_table(log)
    old=next(r for r in rows if r['filename']=='old.svg')
    assert old['status']=='accepted' and old['dl_latest']=='60' and old['custom']=='preserve'
    assert next(r for r in rows if r['filename']=='a.svg')['submitted']==''

def test_latest_downloads_reported_without_guessing_30day_sales(tmp_path):
    meta, log, src = tmp_path/'metadata.csv', tmp_path/'production_log.csv', tmp_path/'scrape.csv'
    metadata(meta); initialize_tracking(meta,log)
    scrape(src,[dict(title='Cyber icon set',downloads='60',last_seen='2026-09-26',in_review='0')])
    assert import_downloads(src,meta,log)['matched']==1
    rows,_=read_table(log)
    assert rows[0]['accepted_date']=='' and rows[0]['first_seen_accepted']=='2026-09-26'
    report=build_report(log,date(2026,9,26),1)
    row=next(iter(report.values()))
    assert row['downloads']==60
    assert row['downloads_per_observed_asset_30d'] is None
    assert row['verdict'].startswith('HOLD')

def test_ambiguous_title_never_assigns_sales_to_last_asset(tmp_path):
    meta,log,src=tmp_path/'meta.csv',tmp_path/'production_log.csv',tmp_path/'scrape.csv'
    metadata(meta,True);initialize_tracking(meta,log)
    scrape(src,[dict(title='Cyber icon set',downloads='99',last_seen='2026-09-26',in_review='0')])
    assert import_downloads(src,meta,log)['ambiguous']==1
    assert sum(int(r.get('dl_latest') or 0) for r in read_table(log)[0])==0

def test_import_idempotency_stale_data_and_explicit_status(tmp_path):
    meta,log,src=tmp_path/'meta.csv',tmp_path/'production_log.csv',tmp_path/'scrape.csv'
    metadata(meta);initialize_tracking(meta,log)
    scrape(src,[dict(title='Cyber icon set',downloads='0',last_seen='2026-09-26',in_review='0')])
    import_downloads(src,meta,log)
    assert read_table(log)[0][0]['status']=='ready'
    scrape(src,[dict(filename='a.svg',downloads='12',last_seen='2026-09-26',status='accepted',accepted_date='2026-08-20',adobe_asset_id='100')])
    import_downloads(src,meta,log);import_downloads(src,meta,log)
    assert len(read_table(tmp_path/'download_history.csv')[0])==1
    scrape(src,[dict(adobe_asset_id='100',downloads='2',last_seen='2026-09-01',status='accepted')])
    import_downloads(src,meta,log)
    row=read_table(log)[0][0]
    assert row['dl_latest']=='12' and row['accepted_date']=='2026-08-20'

def test_decision_requires_real_window_and_enough_assets(tmp_path):
    log=tmp_path/'production_log.csv'
    rows=[dict(filename=f'{i}.svg',niche='cyber',status='accepted',dl_latest='10') for i in range(10)]
    save_log(log,rows)
    samples=[]
    for r in rows:
        samples += [dict(filename=r['filename'],observed_date='2026-08-27',downloads=8,royalty_usd=''),dict(filename=r['filename'],observed_date='2026-09-26',downloads=10,royalty_usd='')]
    write_csv(tmp_path/'download_history.csv',SNAPSHOT_FIELDS,samples)
    group=build_report(log,date(2026,9,26))['cyber']
    assert group['downloads']==100 and group['downloads_per_observed_asset_30d']==2
    assert group['verdict']=='EXPAND TEST'
    assert build_report(log,date(2026,10,26))['cyber']['verdict'].startswith('HOLD')

def test_filename_inference_does_not_turn_airline_into_line_style():
    assert extract_niche_style_batch('airline_solid_20260926060136.svg') == ('airline','solid','2026-09-26')
    assert extract_niche_style_batch('cyber_20261340.svg')[2] == ''


def test_same_day_older_scrape_cannot_lower_recorded_downloads(tmp_path):
    meta,log,src=tmp_path/'meta.csv',tmp_path/'production_log.csv',tmp_path/'scrape.csv'
    metadata(meta);initialize_tracking(meta,log)
    scrape(src,[dict(title='Cyber icon set',downloads='12',last_seen='2026-09-26')])
    import_downloads(src,meta,log)
    scrape(src,[dict(title='Cyber icon set',downloads='2',last_seen='2026-09-26')])
    assert import_downloads(src,meta,log)['invalid']==1
    assert read_table(log)[0][0]['dl_latest']=='12'
