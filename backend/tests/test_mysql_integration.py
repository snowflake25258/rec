"""Opt-in MySQL tests; never point this at a live business database."""
from __future__ import annotations
import os
from uuid import uuid4
import time
import pytest
from backend.business import BusinessStore
from backend.store import Config
from backend.outbox import Publisher

@pytest.mark.skipif(not os.getenv('MYSQL_TEST_DATABASE'), reason='MySQL test database not configured')
def test_real_mysql_transactions_and_outbox():
    name=os.environ['MYSQL_TEST_DATABASE']
    if not name.endswith('_test'):
        pytest.fail('MYSQL_TEST_DATABASE must end with _test')
    business=BusinessStore(Config(mysql_database=name, business_backend='mysql', seed_catalog=True))
    user='test-'+uuid4().hex[:16]
    try:
        payload=dict(event_id=str(uuid4()),user_id=user,item_id='v001',action='favorite',timestamp=time.time())
        assert business.record(payload)
        assert not business.record(payload)
        assert business.state(user)['saved'] == ['v001']
        received=[]
        Publisher(business,received.append).flush(limit=100)
        assert payload['event_id'] in {e['event_id'] for e in received}
        business.record({**payload,'event_id':str(uuid4()),'action':'unfavorite','timestamp':time.time()})
        assert business.state(user)['saved'] == []
    finally:
        business.close()

@pytest.mark.skipif(not os.getenv('MYSQL_TEST_DATABASE'), reason='MySQL test database not configured')
def test_real_mysql_analytics_features_and_model_versions(tmp_path):
    from dataclasses import replace
    from backend.store import Store
    from backend.training.registry import Registry
    name=os.environ['MYSQL_TEST_DATABASE']
    assert name.endswith('_test')
    config=Config(mysql_database=name,business_backend='mysql',seed_catalog=True,mode='demo',seed_analytics=False)
    business=BusinessStore(config)
    analytics=Store(config,business.engine)
    registry=Registry(business,str(tmp_path/'models'))
    user='analytics-'+uuid4().hex[:12]
    try:
        payload=dict(event_id=str(uuid4()),user_id=user,item_id='v001',action='like',timestamp=time.time())
        analytics.append(payload)
        analytics.append(payload)
        feature=next(f for f in analytics.features() if f['user_id']==user)
        assert feature['preference']==3
        matched=[e for e in analytics.events() if e['event_id']==payload['event_id']]
        assert len(matched)==1
        assert abs(matched[0]['timestamp']-payload['timestamp'])<.0011
        analytics.append({**payload,'event_id':str(uuid4()),'action':'unlike','timestamp':time.time()})
        assert next(f for f in analytics.features() if f['user_id']==user)['preference']==0
        base=time.time()-100
        for i in range(40):
            analytics.append(dict(event_id=str(uuid4()),user_id=user,item_id=f'v{1+i%8:03d}',
                                  action='view',timestamp=base+i))
        version=registry.submit(business.catalog(),analytics.events(),'als',4,2,42)
        registry.future.result(timeout=20)
        assert registry.version(version)['status']=='ready'
        registry.activate(version)
        assert registry.active('als')['id']==version
        response=registry.recommendations('als',user,business.catalog(),analytics.events(),5,analytics.features())
        assert response['model_version']==version and len(response['items'])==5
        registry.deactivate(version)
        # Artifacts belong to this test's temporary directory, so leave the test version inactive.
    finally:
        registry.close()
        analytics.close()
        business.close()
