from __future__ import annotations
import time
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from backend.business import BusinessStore, EventConflict, outbox, videos
from backend.outbox import Publisher
from backend.store import Config
from backend.tests.test_recommendations import client, register

@pytest.fixture
def business(tmp_path):
    store = BusinessStore(Config(mode='demo', business_backend='sqlite',
                                business_database=str(tmp_path/'business.sqlite3')))
    yield store
    store.close()

def event(action='favorite', user='alice', item='v002', event_id=None):
    return dict(event_id=event_id or str(uuid4()), user_id=user, item_id=item,
                action=action, timestamp=time.time())

def test_user_state_survives_reconnect(business):
    business.record(event('like'))
    business.record(event('favorite'))
    business.record(event('follow'))
    path=business.engine.url.database
    second=BusinessStore(Config(mode='demo', business_backend='sqlite', business_database=path))
    try:
        assert second.state('alice') == {'liked':['v002'], 'saved':['v002'], 'following':['creator-2']}
        assert second.state('bob') == {'liked':[], 'saved':[], 'following':[]}
    finally:
        second.close()

def test_idempotency_and_conflicting_id(business):
    e=event()
    assert business.record(e)
    assert not business.record({**e, 'timestamp':time.time()})
    with pytest.raises(EventConflict):
        business.record({**e, 'action':'like'})
    assert business.outbox_status()['pending_events'] == 1

def test_repeated_state_is_not_double_counted(business):
    business.record(event('like'))
    business.record(event('like'))
    business.record(event('follow'))
    business.record(event('follow',item='v008'))  # Same creator, different video.
    assert business.outbox_status()['pending_events'] == 2
    assert business.state('alice')['following'] == ['creator-2']

@pytest.mark.parametrize('positive,negative,key', [('like','unlike','liked'),('favorite','unfavorite','saved'),('follow','unfollow','following')])
def test_reversible_interactions(business,positive,negative,key):
    business.record(event(positive))
    assert len(business.state('alice')[key]) == 1
    business.record(event(negative))
    assert business.state('alice')[key] == []
    assert business.outbox_status()['pending_events'] == 2

def test_missing_video_rolls_back(business):
    with pytest.raises(LookupError):
        business.record(event(item='missing'))
    assert business.outbox_status()['pending_events'] == 0
    assert business.state('alice')['saved'] == []

def test_transaction_rolls_back_on_enqueue_error(business,monkeypatch):
    from sqlalchemy.engine import Connection
    execute=Connection.execute
    def fail_outbox(connection, statement, *args, **kwargs):
        if getattr(statement,'is_insert',False) and getattr(statement,'table',None) is outbox:
            raise RuntimeError('simulated database write failure')
        return execute(connection,statement,*args,**kwargs)
    monkeypatch.setattr(Connection,'execute',fail_outbox)
    with pytest.raises(RuntimeError):
        business.record(event())
    assert business.state('alice')['saved'] == []

def test_outbox_failure_keeps_business_and_retries(business):
    e=event()
    business.record(e)
    def unavailable(payload):
        raise ConnectionError('Kafka unavailable')
    worker=Publisher(business,unavailable)
    assert worker.flush() == 0
    assert business.state('alice')['saved'] == ['v002']
    assert business.outbox_status() == {'backend':'sqlite','pending_events':1,'delivery_error':True}
    delivered=[]
    worker.deliver=delivered.append
    assert worker.flush() == 1
    assert delivered[0]['event_id'] == e['event_id']
    assert worker.flush() == 0
    assert business.outbox_status()['pending_events'] == 0

def test_catalog_reads_database_not_static_seed(business):
    with business.engine.begin() as db:
        db.execute(videos.update().where(videos.c.id=='v001').values(title='来自业务库的视频标题'))
        db.execute(videos.update().where(videos.c.id=='v002').values(published=False))
    result=business.catalog()
    assert result[0]['title'] == '来自业务库的视频标题'
    assert 'v002' not in {v['id'] for v in result}
    business.seed()  # Restarts never overwrite edited business metadata.
    assert business.catalog()[0]['title'] == '来自业务库的视频标题'

def test_duplicate_video_urls_are_repaired(business):
    canonical={v['id']:v for v in business.catalog()}
    with business.engine.begin() as db:
        db.execute(videos.update().where(videos.c.id=='v002').values(
            video_url=canonical['v001']['video_url'], title='重复视频'))
    business.seed()
    result=business.catalog()
    assert len({v['video_url'] for v in result}) == len(result) == 24
    assert next(v for v in result if v['id']=='v002')['title'] == canonical['v002']['title']

def test_mysql_required_in_production(tmp_path):
    with pytest.raises(ValueError,match='sqlite'):
        BusinessStore(Config(mode='production',business_backend='sqlite',business_database=str(tmp_path/'x')))
    with pytest.raises(ValueError,match='MYSQL_PASSWORD'):
        BusinessStore(Config(business_backend='mysql',mysql_password=''))

def test_api_persistence_and_conflict(client):
    alice_headers, alice = register(client, 'alice_api')
    bob_headers, bob = register(client, 'bob_api')
    payload=event('favorite', user=alice['user']['id'])
    assert client.post('/api/events',json=payload,headers=alice_headers).status_code == 202
    assert client.get('/api/me/state',headers=alice_headers).json()['saved'] == ['v002']
    assert client.get('/api/me/state',headers=bob_headers).json()['saved'] == []
    assert client.get(f"/api/users/{alice['user']['id']}/state",headers=bob_headers).status_code == 403
    assert client.post('/api/events',json={**payload,'action':'like'},headers=alice_headers).status_code == 409
    assert client.post('/api/events',json=event('unfavorite',user=alice['user']['id']),headers=alice_headers).status_code == 202
    assert client.get('/api/me/state',headers=alice_headers).json()['saved'] == []
    assert client.get('/api/business/status', headers=alice_headers).json()['pending_events'] == 0
    assert len(client.get('/api/videos').json()['items']) == 24
