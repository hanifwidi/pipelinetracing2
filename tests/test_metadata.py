import json
from pathlib import Path
from unittest.mock import Mock
import pytest
import requests
from PIL import Image
from config import cfg
from utils.metadata_ai import _clean_metadata, _post, generate_metadata, _cache_path, PROMPT_VERSION
from utils.csv_exporter import append_metadata_csv
from utils.tracking import read_table

VALID = {'title':'Cyber security icon set', 'keywords':['security','cyber','lock','shield','privacy']}

def test_metadata_rejects_empty_title_and_string_keyword_list():
    with pytest.raises(ValueError): _clean_metadata({**VALID,'title':''})
    with pytest.raises(ValueError): _clean_metadata({**VALID,'keywords':'security,cyber'})
    assert _clean_metadata({**VALID,'keywords':VALID['keywords']+['SECURITY']})['keywords']==VALID['keywords']

def test_no_api_key_marks_metadata_pending_and_never_caches_dummy(tmp_path):
    png=tmp_path/'icon.png';Image.new('RGB',(32,32),'white').save(png)
    result=generate_metadata(png)
    assert result['source']=='dummy'
    assert not _cache_path(png).exists()

def test_429_retries_are_bounded_and_respect_retry_after(monkeypatch):
    import utils.metadata_ai as module
    first=Mock(status_code=429,headers={'Retry-After':'3'})
    second=Mock(status_code=200,headers={});second.json.return_value={'ok':True}
    monkeypatch.setattr(module,'_pace',lambda _:None)
    sleep=Mock();monkeypatch.setattr(module.time,'sleep',sleep)
    post=Mock(side_effect=[first,second]);monkeypatch.setattr(module.requests,'post',post)
    assert _post('test','https://example.invalid',{}, {},1)=={'ok':True}
    assert post.call_count==2 and sleep.call_args.args==(3.0,)

def test_401_is_not_retried(monkeypatch):
    import utils.metadata_ai as module
    response=Mock(status_code=401,headers={})
    response.raise_for_status.side_effect=requests.HTTPError('unauthorized')
    post=Mock(return_value=response);monkeypatch.setattr(module.requests,'post',post)
    monkeypatch.setattr(module,'_pace',lambda _:None)
    with pytest.raises(requests.RequestException, match='HTTP 401'): _post('test','https://example.invalid',{}, {},2)
    assert post.call_count==1

def test_vision_cache_and_force_refresh(tmp_path,monkeypatch):
    import utils.metadata_ai as module
    png=tmp_path/'icon.png';Image.new('RGB',(32,32),'white').save(png)
    monkeypatch.setenv('GEMINI_API_KEY','test-not-a-real-key')
    data={'candidates':[{'content':{'parts':[{'text':json.dumps(VALID)}]}}]}
    post=Mock(return_value=data);monkeypatch.setattr(module,'_post',post)
    assert generate_metadata(png)['source']=='ai'
    assert generate_metadata(png)['source']=='ai' and post.call_count==1
    assert generate_metadata(png,force=True)['source']=='ai' and post.call_count==2
    assert json.loads(_cache_path(png).read_text())['prompt_version']==PROMPT_VERSION

def test_csv_updates_rows_instead_of_appending_duplicates(tmp_path):
    target=tmp_path/'metadata.csv'
    append_metadata_csv(target,'a.svg','Old',VALID['keywords'],category='1')
    append_metadata_csv(target,'a.svg','New',VALID['keywords'])
    rows,_=read_table(target)
    assert len(rows)==1 and rows[0]['Title']=='New' and rows[0]['Category']=='1'
