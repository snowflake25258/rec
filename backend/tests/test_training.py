from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from threading import Event
import numpy as np
import pytest
from backend.training.data import prepare, ranking_metrics
from backend.training.models import fit, gradient
from backend.training.artifacts import save, load
from backend.training.registry import Registry
from backend.business import BusinessStore
from backend.store import Config, Store
from backend.tests.test_recommendations import client, register
import backend.main as main

@pytest.fixture
def data(tmp_path):
    store=Store(Config(mode='demo',business_backend='sqlite',seed_analytics=True,database=str(tmp_path/'events.sqlite3')))
    from backend.catalog import catalog
    result=prepare(catalog(),store.events())
    store.close()
    return result

@pytest.fixture
def registry(tmp_path):
    business=BusinessStore(Config(mode='demo',business_backend='sqlite',business_database=str(tmp_path/'business.sqlite3')))
    registry=Registry(business,str(tmp_path/'models'))
    yield registry
    registry.close()
    business.close()

@pytest.mark.parametrize('algorithm',['als','fm','two_tower'])
def test_train_loss_finite_decreases_and_reproducible(data,algorithm):
    a,loss=fit(data,algorithm,factors=6,epochs=12)
    b,other=fit(data,algorithm,factors=6,epochs=12)
    assert np.all(np.isfinite(loss))
    assert loss[-1] < loss[0]
    for key in a.params:
        np.testing.assert_array_equal(a.params[key],b.params[key])
    assert a.scores('missing-user') is None
    assert np.all(np.isfinite(a.scores(data.users[0])))

@pytest.mark.parametrize('algorithm',['fm','two_tower'])
def test_backprop_matches_numerical_gradient(data,algorithm):
    model,_=fit(data,algorithm,factors=4,epochs=1)
    u,j,y=np.array([0,0,1]),np.array([0,2,3]),np.array([1.,0.,1.])
    args=(u,j,y,data.item_categories,len(data.users),len(data.items))
    _,grads=gradient(algorithm,model.params,*args)
    for key,values in model.params.items():
        idx=np.unravel_index(np.argmax(np.abs(grads[key])),values.shape)
        original=values[idx]
        values[idx]=original+1e-5
        plus,_=gradient(algorithm,model.params,*args)
        values[idx]=original-1e-5
        minus,_=gradient(algorithm,model.params,*args)
        values[idx]=original
        assert grads[key][idx] == pytest.approx((plus-minus)/2e-5,abs=1e-7,rel=1e-4), key


def test_temporal_split_excludes_future_feedback():
    items=[dict(id=f'v{i}',category=str(i%2)) for i in range(5)]
    events=[dict(event_id=str(i),item_id=f'v{i%2}',user_id=f'u{i%3}',action='like',timestamp=i) for i in range(20)]
    events += [dict(event_id=str(i),item_id='v4',user_id='u0',action='favorite',timestamp=i) for i in range(20,25)]
    data=prepare(items,events)
    assert np.all(data.matrix[:,4] == 0)
    assert data.validation[0] == {4}
    changed=[{**e,'action':'skip'} if e['timestamp']>=data.cutoff else e for e in events]
    other=prepare(items,changed)
    np.testing.assert_array_equal(data.matrix,other.matrix)
    for algorithm in ['als','fm','two_tower']:
        first,_=fit(data,algorithm,epochs=2)
        second,_=fit(other,algorithm,epochs=2)
        for key in first.params:
            np.testing.assert_array_equal(first.params[key],second.params[key])


def test_ranking_metrics_known_answer(data):
    scores=np.zeros(len(data.items));scores[2]=3;scores[3]=2
    matrix=np.zeros_like(data.matrix);matrix[0,0]=1
    test=replace(data,matrix=matrix,validation={0:{2,3}})
    metrics=ranking_metrics({0:scores},test)
    assert metrics['recall_at_5'] == 1
    assert metrics['ndcg_at_5'] == 1
    empty=ranking_metrics({},replace(data,validation={}))
    assert empty['recall_at_5'] is None
    assert empty['evaluated_users'] == 0

@pytest.mark.parametrize('algorithm',['als','fm','two_tower'])
def test_model_artifact_roundtrip_and_integrity(tmp_path,data,algorithm):
    model,_=fit(data,algorithm,epochs=2)
    path,digest=save(tmp_path,'version',model,data,{'epochs':2})
    restored=load(path,digest)
    np.testing.assert_array_equal(model.scores(data.users[0]),restored.scores(data.users[0]))
    path.write_bytes(path.read_bytes()+b'corrupted')
    with pytest.raises(ValueError,match='校验'):
        load(path,digest)


def snapshot(registry,tmp_path):
    analytics=Store(Config(mode='demo',business_backend='sqlite',seed_analytics=True,database=str(tmp_path/'analytics.sqlite3')))
    return registry.business.catalog(),analytics.events()


def test_registry_lifecycle_and_rollback(registry,tmp_path):
    items,events=snapshot(registry,tmp_path)
    version=registry.submit(items,events,'als',6,2,42)
    registry.future.result(timeout=15)
    row=registry.versions()[0]
    assert row['status']=='ready' and not row['active']
    assert row['evaluation']['evaluated_users']>0
    with pytest.raises(LookupError):
        registry.recommendations('als','u001',items,events,5)
    registry.activate(version)
    result=registry.recommendations('als','u001',items,events,5)
    assert len(result['items'])==5 and result['model_version']==version
    assert registry.recommendations('als','unknown',items,events,5)['fallback']=='unknown_user'
    second=registry.submit(items,events,'als',6,2,8)
    registry.future.result(timeout=15)
    registry.activate(second)
    assert registry.active('als')['id']==second
    registry.activate(version)
    assert registry.active('als')['id']==version
    assert sum(v['active'] for v in registry.versions())==1
    registry.deactivate(version)
    assert registry.active('als') is None


def test_failed_training_and_busy_queue(registry,tmp_path,monkeypatch):
    import backend.training.registry as module
    items,events=snapshot(registry,tmp_path)
    entered,release=Event(),Event()
    def fail(*args,**kwargs):
        entered.set()
        release.wait(timeout=5)
        raise ValueError('受控训练失败')
    monkeypatch.setattr(module,'fit',fail)
    registry.submit(items,events,'fm',4,2,42)
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(RuntimeError,match='运行中'):
            registry.submit(items,events,'als',4,2,42)
    finally:
        release.set()
    registry.future.result(timeout=10)
    version=registry.versions()[0]
    assert version['status']=='failed' and version['error']=='受控训练失败'
    with pytest.raises(ValueError,match='完成训练'):
        registry.activate(version['id'])


def test_api_train_activate_inference(client):
    headers,_=register(client,'trainer')
    assert client.get('/api/recommendations?algorithm=two_tower',headers=headers).status_code==409
    assert client.post('/api/models/train',json={'algorithm':'two_tower','epochs':100}).status_code==401
    assert client.post('/api/models/train',json={'algorithm':'two_tower','epochs':100},headers=headers).status_code==422
    result=client.post('/api/models/train',json={'algorithm':'two_tower','epochs':3,'factors':4},headers=headers)
    assert result.status_code==202
    version=result.json()['id']
    main.registry.future.result(timeout=15)
    assert client.get('/api/models',headers=headers).json()['items'][0]['status']=='ready'
    assert client.post(f'/api/models/{version}/activate',headers=headers).status_code==200
    response=client.get('/api/recommendations?algorithm=two_tower&limit=5',headers=headers).json()
    assert response['model_version']==version and len(response['items'])==5
    algorithms=client.get('/api/algorithms',headers=headers).json()['items']
    assert next(a for a in algorithms if a['id']=='two_tower')['status']=='active'
    assert client.post(f'/api/models/{version}/deactivate',headers=headers).status_code==200
    assert client.get('/api/recommendations?algorithm=two_tower',headers=headers).status_code==409
    assert client.post('/api/models/missing/activate',headers=headers).status_code==404


def test_model_version_survives_service_restart(registry,tmp_path):
    items,events=snapshot(registry,tmp_path)
    version=registry.submit(items,events,'fm',4,2,42)
    registry.future.result(timeout=15)
    registry.activate(version)
    expected=registry.recommendations('fm','u001',items,events,4)
    second=Registry(registry.business,str(tmp_path/'models'))
    try:
        assert second.active('fm')['id']==version
        assert second.recommendations('fm','u001',items,events,4)==expected
    finally:
        second.close()


def test_interrupted_job_recovers_to_failed(registry,tmp_path):
    from backend.business import model_versions
    with registry.business.engine.begin() as db:
        db.execute(model_versions.insert().values(id='interrupted',algorithm='als',artifact_path='',
            metrics={'status':'running','config':{}},created_at=0,active=False))
    second=Registry(registry.business,str(tmp_path/'models'))
    try:
        assert second.version('interrupted')['status']=='failed'
    finally:
        second.close()


def test_corrupt_artifact_cannot_activate(registry,tmp_path):
    items,events=snapshot(registry,tmp_path)
    version=registry.submit(items,events,'als',4,2,42)
    registry.future.result(timeout=15)
    (tmp_path/'models'/f'{version}.npz').write_bytes(b'broken')
    with pytest.raises(ValueError,match='校验'):
        registry.activate(version)
    assert registry.active('als') is None


def test_models_api_requires_auth(client):
    assert client.get('/api/models').status_code==401
    assert client.post('/api/models/train',json={'algorithm':'als'}).status_code==401
    headers,_=register(client,'model_trainer')
    assert client.get('/api/models',headers=headers).status_code==200
