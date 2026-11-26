from __future__ import annotations
import math
import time
from uuid import uuid4
import pytest
from backend.algorithms import ALGORITHMS, recommend
from backend.catalog import catalog

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
