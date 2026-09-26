import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from PIL import Image, ImageDraw
from utils.tracking import read_table

REPO = Path(__file__).resolve().parents[1]

def image(path, shape='square'):
    path.parent.mkdir(parents=True,exist_ok=True)
    im=Image.new('RGB',(256,256),'white')
    draw=ImageDraw.Draw(im)
    if shape=='square': draw.rectangle((48,48,208,208),fill='black')
    else: draw.ellipse((32,32,220,220),fill=(20,80,160))
    im.save(path)

def cli(tmp_path, *args):
    if not shutil.which('inkscape'):
        pytest.skip('Inkscape not installed')
    env=os.environ.copy()
    for key in ('GEMINI_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','MISTRAL_API_KEY'):
        env.pop(key,None)
    result=subprocess.run([sys.executable,str(REPO/'main.py'),*args],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=90)
    return result

def test_spawn_workers_eps_and_pending_metadata_are_not_archived(tmp_path):
    image(tmp_path/'input/a/logo.png')
    image(tmp_path/'input/b/logo.png','circle')
    result=cli(tmp_path,'--workers','2','--eps')
    assert result.returncode==0, result.stdout+result.stderr
    manifest=json.loads((tmp_path/'tracking/pipeline_manifest.json').read_text())
    assets=list(manifest['assets'].values())
    assert len(assets)==2
    assert all(a['status']=='needs_metadata' for a in assets)
    assert all(Path(a['eps']).exists() for a in assets)  # --eps survives spawn
    assert len(list((tmp_path/'output_svg').glob('*.svg')))==2
    assert len(list((tmp_path/'input').rglob('*.png')))==2
    assert not (tmp_path/'output_svg/metadata.csv').exists()
    rows,_=read_table(tmp_path/'output_svg/review.csv')
    assert len(rows)==2 and len({r['Filename'] for r in rows})==2

def test_manual_metadata_ready_resume_idempotency_and_archive(tmp_path):
    image(tmp_path/'input/asset.png')
    with (tmp_path/'manual.csv').open('w',newline='') as stream:
        w=csv.writer(stream);w.writerow(['Filename','Title','Keywords','Category']);w.writerow(['asset.png','Black square icon','square,black,icon,shape,geometry','8'])
    args=('--workers','1','--metadata-csv','manual.csv','--no-archive')
    result=cli(tmp_path,*args)
    assert result.returncode==0, result.stdout+result.stderr
    manifest=json.loads((tmp_path/'tracking/pipeline_manifest.json').read_text())
    asset=next(iter(manifest['assets'].values()))
    assert asset['status']=='ready',asset
    assert asset['quality']['passed']
    again=cli(tmp_path,*args)
    assert again.returncode==0,again.stdout+again.stderr
    asset=next(iter(json.loads((tmp_path/'tracking/pipeline_manifest.json').read_text())['assets'].values()))
    assert asset['trace_cache_hit']
    rows = read_table(tmp_path/'output_svg/metadata.csv')[0]
    assert len(rows)==1 and rows[0]['Category']=='8'
    archived=cli(tmp_path,'--workers','1','--metadata-csv','manual.csv')
    assert archived.returncode==0,archived.stdout+archived.stderr
    assert not (tmp_path/'input/asset.png').exists()
    assert len(list((tmp_path/'input_processed').glob('*.png')))==1

def test_corrupt_input_has_nonzero_exit_and_preserves_original(tmp_path):
    (tmp_path/'input').mkdir()
    (tmp_path/'input/broken.png').write_bytes(b'not an image')
    result=cli(tmp_path,'--workers','1')
    assert result.returncode==1
    assert (tmp_path/'input/broken.png').exists()
    assert len(list((tmp_path/'quarantine').rglob('broken.png')))==1
    manifest=json.loads((tmp_path/'tracking/pipeline_manifest.json').read_text())
    assert next(iter(manifest['assets'].values()))['status']=='failed'
