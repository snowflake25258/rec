from __future__ import annotations
import math
import time
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from backend.algorithms import ALGORITHMS, recommend
from backend.catalog import catalog
from backend.store import Config, Store
import backend.main as main

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'config', Config(mode='demo', database=str(tmp_path/'events.sqlite3'),
        seed_analytics=True,business_backend='sqlite', business_database=str(tmp_path/'business.sqlite3'),model_directory=str(tmp_path/'models'),media_directory=str(tmp_path/'media')))
    with TestClient(main.app) as c:
        yield c

def register(client, username='tester', password='password123', name=''):
    response = client.post('/api/auth/register', json={'username':username,'password':password,'name':name})
    assert response.status_code == 201, response.text
    data = response.json()
    return {'Authorization': f"Bearer {data['token']}"}, data

@pytest.mark.parametrize('algorithm', [a[0] for a in ALGORITHMS])
def test_algorithms_have_finite_unique_results(algorithm):
    items = catalog()
    events = [dict(user_id=f'u{i%4}', item_id=items[i%10]['id'], action='like', timestamp=float(i)) for i in range(30)]
    result = recommend(items, events, 'u1', algorithm, 8)
    assert len(result) == len({v['id'] for v in result}) == 8
    assert all(math.isfinite(v['score']) for v in result)
    assert all(result[i]['score'] >= result[i+1]['score'] for i in range(7)) if algorithm != 'mmr' else True

@pytest.mark.parametrize('algorithm', [a[0] for a in ALGORITHMS])
def test_cold_start_and_empty(algorithm):
    assert recommend([], [], 'new', algorithm) == []
    assert len(recommend(catalog()[:1], [], 'new', algorithm)) == 1
    assert len(recommend(catalog(), [], 'new', algorithm)) == 10

def test_content_adapts_to_feedback():
    items = catalog()
    events = [dict(user_id='new', item_id='v002', action='favorite', timestamp=time.time())]
    result = recommend(items, events, 'new', 'content', 3)
    assert all(v['category'] == '生活' for v in result)

def test_production_features_are_used():
    features = [dict(user_id='new', item_id='v004', preference=8.)]
    result = recommend(catalog(), [], 'new', 'content', 3, features)
    assert all(v['category'] == '美食' for v in result)

def test_unknown_algorithm():
    with pytest.raises(ValueError):
        recommend(catalog(), [], 'u001', 'fake')

def test_event_round_trip_and_idempotency(client):
    headers, user = register(client, 'test')
    before = client.get('/api/metrics', headers=headers).json()['events']
    payload = dict(user_id=user['user']['id'], item_id='v002', action='favorite', event_id=str(uuid4()))
    assert client.post('/api/events', json=payload, headers=headers).status_code == 202
    assert client.post('/api/events', json=payload, headers=headers).status_code == 202
    assert client.get('/api/metrics', headers=headers).json()['events'] == before+1
    result = client.get('/api/recommendations?algorithm=content&limit=3', headers=headers)
    assert result.status_code == 200
    assert all(v['category'] == '生活' for v in result.json()['items'])

def test_validation_and_static(client):
    assert client.get('/').status_code == 200
    assert client.get('/app.js').status_code == 200
    assert client.get('/api/recommendations?algorithm=nonexistent').status_code == 401
    headers, _ = register(client, 'validator')
    assert client.get('/api/recommendations?algorithm=nonexistent', headers=headers).status_code == 422
    assert client.get('/api/recommendations?limit=200', headers=headers).status_code == 422
    assert client.get('/api/recommendations?user_id=bad%20user', headers=headers).status_code == 422
    assert client.get('/api/recommendations?user_id=someone_else', headers=headers).status_code == 403
    assert client.post('/api/events', json=dict(item_id='invalid', action='like'), headers=headers).status_code == 404
    assert client.post('/api/events', json=dict(item_id='v001', action='invalid'), headers=headers).status_code == 422

def test_requires_login(client):
    for path in ('/api/recommendations', '/api/me/state', '/api/users/u001/state',
                 '/api/metrics', '/api/models', '/api/algorithms', '/api/business/status'):
        assert client.get(path).status_code == 401, path
    assert client.post('/api/events', json=dict(item_id='v001', action='view')).status_code == 401
    assert client.get('/api/videos').status_code == 200

def test_user_identity_cannot_be_spoofed(client):
    headers, user = register(client, 'alice')
    other, other_user = register(client, 'bob')
    assert client.get(f"/api/users/{user['user']['id']}/state", headers=other).status_code == 403
    response = client.post('/api/events', json=dict(user_id=other_user['user']['id'], item_id='v001', action='like'), headers=headers)
    assert response.status_code == 403
    assert client.get('/api/me/state', headers=headers).json()['liked'] == []
    assert client.get(f"/api/users/{user['user']['id']}/state", headers=headers).status_code == 200

def test_auth(client):
    assert client.get('/api/metrics').status_code == 401
    headers, _ = register(client, 'metrics_user')
    assert client.get('/api/metrics', headers=headers).status_code == 200
