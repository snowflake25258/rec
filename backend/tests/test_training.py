from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import numpy as np
import pytest
from backend.training.data import prepare, ranking_metrics
from backend.training.models import fit, gradient
from backend.training.artifacts import save, load

@pytest.fixture
def data():
    import random
    from backend.catalog import catalog
    rng=random.Random(42)
    events=[]
    for i in range(650):
        user=f'u{rng.randrange(1,31):03d}'
        topic=int(user[1:])%6
        item=rng.choice([j+1 for j in range(24) if j%6==topic] if rng.random()<.7 else list(range(1,25)))
        events.append(dict(event_id=f'sample-{i}',user_id=user,item_id=f'v{item:03d}',
            action=rng.choice(['view','like','complete','favorite']),timestamp=float(i)))
    return prepare(catalog(),events)

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
