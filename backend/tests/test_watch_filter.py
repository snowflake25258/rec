"""Watch exclusions are tested with in-memory samples, never a database."""
from __future__ import annotations
from collections import OrderedDict
from threading import RLock
from types import SimpleNamespace
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.algorithms import ALGORITHMS,recommend
from backend.catalog import catalog
from backend.training.registry import Registry
import backend.main as main


def watched_event(item,action='view',user='viewer'):
    return dict(user_id=user,item_id=item,action=action,timestamp=1.)


@pytest.mark.parametrize('algorithm',[a[0] for a in ALGORITHMS])
def test_every_baseline_excludes_only_watched_videos_for_this_user(algorithm):
    events=[watched_event('v024'),watched_event('v002','complete'),
            watched_event('v003','like'),watched_event('v004',user='another')]
    result=recommend(catalog(),events,'viewer',algorithm,24)
    ids={v['id'] for v in result}
    assert len(ids)==22
    assert not ids.intersection({'v024','v002'})
    assert {'v003','v004'}<=ids


@pytest.mark.parametrize('algorithm',[a[0] for a in ALGORITHMS])
def test_empty_unwatched_pool_never_backfills_watched_items(algorithm):
    items=catalog()
    assert recommend(items,[],'viewer',algorithm,5,excluded={v['id'] for v in items})==[]


@pytest.mark.parametrize('algorithm',['als','fm','two_tower'])
@pytest.mark.parametrize('known_user',[True,False])
def test_model_and_popularity_backfill_share_watch_exclusions(algorithm,known_user):
    items=catalog()
    model=SimpleNamespace(items=tuple(v['id'] for v in items[:12]),
                          scores=lambda user:np.arange(12,dtype=float) if known_user else None)
    registry=Registry.__new__(Registry)
    registry.lock=RLock()
    registry.cache=OrderedDict([('version',model)])
    registry.active=lambda alg:{'id':'version','algorithm':alg}
    events=[watched_event('v012')]
    response=registry.recommendations(algorithm,'viewer',items,events,24,excluded={'v024'})
    ids={v['id'] for v in response['items']}
    assert len(ids)==22
    assert not ids.intersection({'v012','v024'})
    empty=registry.recommendations(algorithm,'viewer',items,events,24,excluded={v['id'] for v in items})
    assert empty['items']==[]


def test_api_filters_old_history_and_pending_outbox_before_limiting(monkeypatch):
    # Neither watched video is present in the sampled recent events.
    monkeypatch.setattr(main,'store',SimpleNamespace(events=lambda:[],features=lambda:[],watched_ids=lambda user:{'v001'}))
    monkeypatch.setattr(main,'business',SimpleNamespace(catalog=catalog,watched_ids=lambda user:{'v002'},state=lambda user:{}))
    app=FastAPI()
    app.add_api_route('/recommendations',main.recommendations)
    app.add_api_route('/me/state',main.my_state)
    app.dependency_overrides[main.current_user]=lambda:{'id':'viewer'}
    with TestClient(app) as client:
        result=client.get('/recommendations?algorithm=popular&limit=24')
        assert result.status_code==200
        ids={v['id'] for v in result.json()['items']}
        assert len(ids)==22 and not ids.intersection({'v001','v002'})
        assert client.get('/me/state').json()['watched']==['v001','v002']
