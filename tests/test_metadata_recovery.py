"""Exercise real fallback/retry code against simulated HTTP responses only."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate
from unittest.mock import Mock

import pytest
import requests
from PIL import Image

from config import cfg
from utils import metadata_ai as m

VALID = {'title': 'Security icons', 'keywords': ['security', 'lock', 'shield', 'privacy', 'encryption']}
SUCCESS = {'candidates': [{'content': {'parts': [{'text': json.dumps(VALID)}]}}]}


def response(status, body=None, headers=None):
    r = requests.Response()
    r.status_code = status
    r.headers.update(headers or {})
    r._content = json.dumps(body or {}).encode()
    return r


def quota(period='Minute', delay='50.54s', model=True, value='20'):
    return {'error': {'message': 'Please retry in ' + delay + '.', 'details': [
        {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{
            'quotaId': 'GenerateRequestsPer' + period + 'PerProjectPerModel-FreeTier',
            'quotaDimensions': {'model': 'model-a'} if model else {}, 'quotaValue': value}]},
        {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': delay}]}}


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    sleeps = []
    def sleep(seconds):
        assert 0 <= seconds <= 30
        sleeps.append(seconds)
        now[0] += seconds
    monkeypatch.setattr(m.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(m.time, 'sleep', sleep)
    return now, sleeps


@pytest.fixture
def artwork(tmp_path, monkeypatch):
    path = tmp_path / 'preview.png'
    Image.new('RGB', (16, 16), 'white').save(path)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-secret-never-log')
    monkeypatch.setenv('GEMINI_MODEL', 'model-a')
    monkeypatch.setenv('GEMINI_FALLBACK_MODELS', 'model-b,model-c')
    return path


def test_retry_delay_sources_and_no_thirty_second_cap(monkeypatch):
    assert m._retry_delay(response(429, quota()), 0) == 50.54
    assert m._retry_delay(response(429, quota(), {'Retry-After': '75'}), 0) == 75
    assert m._retry_delay(response(429, {'error': {'message': 'Please retry in 50.54s.'}}), 0) == 50.54
    monkeypatch.setattr(m.time, 'time', lambda: 1000)
    assert m._retry_delay(response(503, headers={'Retry-After': formatdate(1090, usegmt=True)}), 0) == 90
    assert m._retry_delay(response(503, headers={'Retry-After': 'nan'}), 2) == 4


def test_429_waits_full_window_and_recovers(artwork, monkeypatch, clock):
    calls = []
    def post(*args, **kwargs):
        calls.append(clock[0][0])
        return response(429, quota()) if len(calls) == 1 else response(200, SUCCESS)
    monkeypatch.setattr(m.requests, 'post', post)
    result = m.generate_metadata(artwork)
    assert result['provider'] == 'gemini:model-a'
    assert calls[1] - calls[0] == pytest.approx(50.54)
    assert sum(clock[1]) >= 50.54


def test_404_then_503_then_fallback_success_and_no_dead_model_reprobe(artwork, monkeypatch, clock):
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        return response(404) if 'model-a:' in url else response(503) if 'model-b:' in url else response(200, SUCCESS)
    monkeypatch.setattr(m.requests, 'post', post)
    assert m.generate_metadata(artwork)['provider'] == 'gemini:model-c'
    assert m.generate_metadata(artwork, force=True)['source'] == 'ai'
    assert sum('model-a:' in url for url in calls) == 1
    assert sum('model-b:' in url for url in calls) == cfg.AI_RETRIES + 1


@pytest.mark.parametrize('period,value', [('Day', '20'), ('Minute', '0')])
def test_daily_or_zero_quota_not_retried(artwork, monkeypatch, clock, period, value):
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        return response(429, quota(period=period, value=value)) if 'model-a:' in url else response(200, SUCCESS)
    monkeypatch.setattr(m.requests, 'post', post)
    result = m.generate_metadata(artwork)
    assert result['provider'] == 'gemini:model-b'
    assert len(calls) == 2
    assert sum(clock[1]) < 50
    assert ('gemini', 'model-a') in m._disabled


def test_project_quota_switches_to_router_and_never_caches_dummy(artwork, monkeypatch, clock):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-router-secret')
    monkeypatch.setenv('OPENROUTER_MODEL', 'vendor/vision')
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        if 'googleapis' in url:
            return response(429, quota(period='Day', model=False))
        return response(200, {'choices': [{'message': {'content': json.dumps(VALID)}}]})
    monkeypatch.setattr(m.requests, 'post', post)
    result = m.generate_metadata(artwork)
    assert result['provider'] == 'openrouter:vendor/vision'
    assert len(calls) == 2
    assert json.loads(m._cache_path(artwork).read_text())['source'] == 'ai'


def test_repeated_429_falls_back_after_bounded_retries(artwork, monkeypatch, clock):
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        return response(429, quota(delay='1s')) if 'model-a:' in url else response(200, SUCCESS)
    monkeypatch.setattr(m.requests, 'post', post)
    assert m.generate_metadata(artwork)['provider'] == 'gemini:model-b'
    assert sum('model-a:' in url for url in calls) == 3


def test_repeated_project_429_falls_back_to_router(artwork, monkeypatch, clock):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-router-key')
    monkeypatch.setenv('OPENROUTER_MODEL', 'vendor/vision')
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        if 'googleapis' in url:
            return response(429, quota(delay='50.54s', model=False))
        return response(200, {'choices': [{'message': {'content': json.dumps(VALID)}}]})
    monkeypatch.setattr(m.requests, 'post', post)
    assert m.generate_metadata(artwork)['provider'] == 'openrouter:vendor/vision'
    assert len(calls) == 4
    assert sum(clock[1]) >= 101.08


def test_long_retry_hint_skips_without_retrying_early(artwork, monkeypatch, clock):
    monkeypatch.setenv('GEMINI_FALLBACK_MODELS', '')
    post = Mock(return_value=response(429, quota(delay='3600s')))
    monkeypatch.setattr(m.requests, 'post', post)
    result = m.generate_metadata(artwork)
    assert result['source'] == 'dummy' and result['keywords'] == []
    assert 'HTTP 429' in result['reason']
    assert post.call_count == 1 and not clock[1]
    assert not m._cache_path(artwork).exists()
    m.generate_metadata(artwork)
    assert post.call_count == 1


def test_timeout_retry_bounded_and_secret_not_logged(artwork, monkeypatch, clock, caplog):
    monkeypatch.setenv('GEMINI_FALLBACK_MODELS', '')
    post = Mock(side_effect=requests.Timeout('https://example.invalid?key=test-secret-never-log'))
    monkeypatch.setattr(m.requests, 'post', post)
    result = m.generate_metadata(artwork)
    assert result['source'] == 'dummy'
    assert post.call_count == 3
    assert 'test-secret-never-log' not in caplog.text + result['reason']


def test_workers_share_provider_pacing(monkeypatch, clock):
    calls = []
    def post(*args, **kwargs):
        calls.append(clock[0][0])
        return response(200, {'ok': True})
    monkeypatch.setattr(m.requests, 'post', post)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda n: m._post('gemini', 'https://example.invalid/model:generateContent', {}, {}, 1), range(6)))
    assert len(results) == 6
    assert all(b-a >= 60 / cfg.AI_REQUESTS_PER_MINUTE for a, b in zip(calls, calls[1:]))


def test_queued_worker_does_not_bypass_quota_cooldown(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(m, '_pace', lambda _: None)
    def post(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return response(429, quota(delay='120s', model=False))
    monkeypatch.setattr(m.requests, 'post', post)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(m._post, 'gemini', 'https://example.invalid/a:generateContent', {}, {}, 0)
        assert entered.wait(5)
        second = pool.submit(m._post, 'gemini', 'https://example.invalid/b:generateContent', {}, {}, 0)
        release.set()
        for future in (first, second):
            with pytest.raises(m.ProviderUnavailable):
                future.result(timeout=5)
    assert len(calls) == 1
