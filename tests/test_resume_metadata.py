import csv
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

import main
from config import cfg
from utils.atomic_io import write_json


@pytest.fixture
def saved_assets(tmp_path, monkeypatch):
    main.setup_directories()
    manifest = {'version': '3.0', 'assets': {}}
    for name, status, passed in [('ready', 'ready', True), ('pending', 'needs_metadata', True), ('review', 'needs_review', False)]:
        source = cfg.INPUT_FOLDER / (name + '.png')
        Image.new('RGB', (8, 8), 'white').save(source)
        digest = main.content_hash(source)
        # Different source contents for distinct asset ids.
        if name != 'ready':
            Image.new('RGB', (8, 8), 'red' if name == 'pending' else 'blue').save(source)
            digest = main.content_hash(source)
        svg = cfg.OUTPUT_SVG_FOLDER / (name + '.svg')
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="5000" height="5000" viewBox="0 0 8 8"><path d="M1 1H7V7H1Z"/></svg>')
        preview = cfg.PREVIEW_FOLDER / (name + '.png')
        Image.new('RGB', (8, 8), 'white').save(preview)
        manifest['assets'][digest] = dict(asset_id=digest, basename=name, status=status,
            sources=[str(source)], svg=str(svg), preview=str(preview), eps=None,
            quality={'passed': passed, 'warnings': [] if passed else ['QA warning']}, production_seconds=1,
            unique_source_name=True)
    path = cfg.TRACKING_FOLDER / 'pipeline_manifest.json'
    write_json(path, manifest)
    manual = tmp_path / 'metadata.csv'
    with manual.open('w', newline='') as stream:
        w = csv.writer(stream)
        w.writerow(['Filename','Title','Keywords','Category'])
        w.writerow(['pending.svg','Security symbols','security,privacy,lock,shield,encryption','8'])
    # Neither tracing nor Inkscape should be required for saved valid previews.
    monkeypatch.setattr(main, 'process_single_image', Mock(side_effect=AssertionError('traced during resume')))
    monkeypatch.setattr(main, 'find_inkscape', Mock(side_effect=AssertionError('unnecessary renderer lookup')))
    return manifest, path, manual


@pytest.mark.parametrize('qa_passed', [True, False])
def test_resume_only_pending_preserves_other_outputs_and_saved_qa(saved_assets, monkeypatch, qa_passed):
    manifest, path, manual = saved_assets
    pending = next(a for a in manifest['assets'].values() if a['status'] == 'needs_metadata')
    pending['quality']['passed'] = qa_passed
    write_json(path, manifest)
    originals = {a['asset_id']: (dict(a), Path(a['svg']).read_bytes(), Path(a['svg']).stat().st_mtime_ns)
                 for a in manifest['assets'].values() if a['status'] != 'needs_metadata'}
    # Resume must also work with no source images in input/.
    for source in cfg.INPUT_FOLDER.glob('*.png'):
        source.unlink()
    assert main.main(['--resume-metadata','--metadata-csv',str(manual),'--no-archive']) == 0
    after = json.loads(path.read_text())['assets']
    for key, (stage, content, mtime) in originals.items():
        assert after[key] == stage
        assert Path(stage['svg']).read_bytes() == content
        assert Path(stage['svg']).stat().st_mtime_ns == mtime
    updated = after[pending['asset_id']]
    assert updated['status'] == ('ready' if qa_passed else 'needs_review')
    assert updated['metadata']['source'] == 'manual'
    assert b'Security symbols' in Path(updated['svg']).read_bytes()
    assert not list(cfg.CACHE_DIR.rglob('raw.svg'))


def test_missing_svg_stays_pending_and_keeps_input(saved_assets):
    manifest, path, manual = saved_assets
    pending = next(a for a in manifest['assets'].values() if a['status'] == 'needs_metadata')
    Path(pending['svg']).unlink()
    assert main.main(['--resume-metadata','--metadata-csv',str(manual)]) == 1
    assert json.loads(path.read_text()) == manifest
    assert Path(pending['sources'][0]).exists()


def test_resume_without_provider_does_not_inject_or_archive(saved_assets):
    manifest, path, manual = saved_assets
    pending = next(a for a in manifest['assets'].values() if a['status'] == 'needs_metadata')
    before = Path(pending['svg']).read_bytes()
    assert main.main(['--resume-metadata']) == 0
    after = json.loads(path.read_text())['assets'][pending['asset_id']]
    assert after['status'] == 'needs_metadata'
    assert Path(pending['svg']).read_bytes() == before
    assert Path(pending['sources'][0]).exists()
    assert not (cfg.OUTPUT_SVG_FOLDER / 'metadata.csv').exists()


@pytest.mark.parametrize('source_changed', [True, False])
def test_resume_archives_only_original_source(saved_assets, source_changed):
    manifest, path, manual = saved_assets
    pending = next(a for a in manifest['assets'].values() if a['status'] == 'needs_metadata')
    source = Path(pending['sources'][0])
    if source_changed:
        source.write_bytes(b'new user file must not be moved')
    assert main.main(['--resume-metadata','--metadata-csv',str(manual)]) == 0
    assert source.exists() == source_changed
    after = json.loads(path.read_text())['assets'][pending['asset_id']]
    assert after['status'] == 'ready'
    if not source_changed:
        assert Path(after['sources'][0]).parent == cfg.INPUT_PROCESSED_FOLDER
